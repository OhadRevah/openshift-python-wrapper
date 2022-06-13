import json
import logging
import shlex

import bitmath
import pexpect
from ocp_resources.deployment import Deployment
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.service import Service
from ocp_resources.service_mesh_member_roll import ServiceMeshMemberRoll
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.network.constants import SERVICE_MESH_PORT
from utilities import console
from utilities.constants import (
    ISTIO_SYSTEM_DEFAULT_NS,
    OS_FLAVOR_CIRROS,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
)
from utilities.infra import run_ssh_commands
from utilities.network import get_vmi_ip_v4_by_name, ping
from utilities.virt import CIRROS_IMAGE, VirtualMachineForTests


LOGGER = logging.getLogger(__name__)
DHCP_SERVICE_RESTART = "sudo systemctl start dhcpd"
DHCP_SERVER_CONF_FILE = """
cat <<EOF >> /etc/dhcp/dhcpd.conf
default-lease-time 3600;
max-lease-time 7200;
authoritative;
subnet {DHCP_IP_SUBNET}.0 netmask 255.255.255.0 {{
option subnet-mask 255.255.255.0;
range {DHCP_IP_RANGE_START} {DHCP_IP_RANGE_END};
}}
EOF
"""
SERVICE_MESH_VM_MEMORY_REQ = "128M"
SERVICE_MESH_INJECT_ANNOTATION = "sidecar.istio.io/inject"


class ServiceMeshDeploymentService(Service):
    def __init__(self, app_name, namespace, port, port_name=None):
        super().__init__(
            name=app_name,
            namespace=namespace,
        )
        self.port = port
        self.app_name = app_name
        self.port_name = port_name

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["selector"] = {"app": self.app_name}
        res["spec"]["ports"] = [
            {
                "port": self.port,
                "protocol": "TCP",
            },
        ]
        if self.port_name:
            res["spec"]["ports"][0]["name"] = self.port_name
        return res


class ServiceMeshMemberRollForTests(ServiceMeshMemberRoll):
    def __init__(
        self,
        members,
    ):
        """
        Service Mesh Member Roll creation
        Args:
            members (list): Namespaces to be added to Service Mesh
        """
        super().__init__(
            name="default",
            namespace=ISTIO_SYSTEM_DEFAULT_NS,
        )
        self.members = members

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {"members": self.members}
        return res


class CirrosVirtualMachineForServiceMesh(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
    ):
        """
        Cirros VM Creation. Used for Service Mesh tests
        """

        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            os_flavor=OS_FLAVOR_CIRROS,
            memory_requests=SERVICE_MESH_VM_MEMORY_REQ,
            image=CIRROS_IMAGE,
        )

    def to_dict(self):
        res = super().to_dict()
        res["spec"]["template"]["metadata"].setdefault("annotations", {})
        res["spec"]["template"]["metadata"]["annotations"] = {
            SERVICE_MESH_INJECT_ANNOTATION: "true",
        }

        return res


class ServiceMeshDeployments(Deployment):
    def __init__(
        self,
        name,
        namespace,
        version,
        image,
        replicas=1,
        command=None,
        strategy=None,
        service_account=False,
        policy="Always",
        service_port=None,
        host=None,
        port=None,
    ):
        self.name = f"{name}-{version}-dp"
        super().__init__(name=self.name, namespace=namespace)
        self.version = version
        self.replicas = replicas
        self.image = image
        self.strategy = strategy
        self.service_account = service_account
        self.policy = policy
        self.port = port
        self.app_name = name
        self.command = command
        self.service_port = service_port
        self.host = host

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["replicas"] = self.replicas
        res["spec"]["selector"] = {
            "matchLabels": {
                "app": self.app_name,
                "version": self.version,
            },
        }
        res["spec"].setdefault("template", {})
        res["spec"]["template"].setdefault("metadata", {})
        res["spec"]["template"]["metadata"]["annotations"] = {
            SERVICE_MESH_INJECT_ANNOTATION: "true"
        }
        res["spec"]["template"]["metadata"]["labels"] = {
            "app": self.app_name,
            "version": self.version,
        }
        res["spec"]["template"].setdefault("spec", {})
        res["spec"]["template"]["spec"]["containers"] = [
            {
                "image": self.image,
                "imagePullPolicy": self.policy,
                "name": self.name,
            }
        ]
        res["spec"]["template"]["spec"]["restartPolicy"] = "Always"
        if self.strategy:
            res["spec"]["strategy"] = self.strategy
        if self.service_account:
            res["spec"]["template"]["spec"]["serviceAccountName"] = self.app_name
        if self.command:
            res["spec"]["template"]["spec"]["containers"][0]["command"] = self.command
        if self.port:
            res["spec"]["template"]["spec"]["containers"][0]["ports"] = [
                {"containerPort": self.port}
            ]
        return res


def assert_no_ping(src_vm, dst_ip, packet_size=None, count=None):
    assert (
        ping(src_vm=src_vm, dst_ip=dst_ip, packet_size=packet_size, count=count)[0]
        == "100"
    )


def update_cloud_init_extra_user_data(cloud_init_data, cloud_init_extra_user_data):
    for key, val in cloud_init_extra_user_data.items():
        if key not in cloud_init_data:
            cloud_init_data.update(cloud_init_extra_user_data)
        else:
            cloud_init_data[key] = cloud_init_data[key] + val


def wait_for_address_on_iface(worker_pod, iface_name):
    """
    This function returns worker's ip else throws 'resources.utils.TimeoutExpiredError: Timed Out:
    if function passed in func argument failed.
    """
    sample = None
    log = "Worker ip address for {iface_name} : {sample}"
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=NodeNetworkState(worker_pod.node.name).ipv4,
        iface=iface_name,
    )
    try:
        for sample in samples:
            if sample:
                LOGGER.info(log.format(iface_name=iface_name, sample=sample))
                return sample
    except TimeoutExpiredError:
        LOGGER.error(log.format(iface_name=iface_name, sample=sample))
        raise


def run_test_guest_performance(server_vm, client_vm, listen_ip=None, target_ip=None):
    """
    In-guest performance bandwidth passthrough.
    VMs should be created with:
        ssh=True,
        username=SSH.USERNAME,
        password=SSH.PASSWORD,

    Args:
        server_vm (VirtualMachine): VM name that will be IPERF server.
        client_vm (VirtualMachine): VM name that will be IPERF client.
        listen_ip (str): The IP to listen on the server, if not sent then "0.0.0.0" will be used.
        target_ip (str): the IP to connect to (server IP), if not sent then listen_ip will be used.
    """
    _listen_ip = listen_ip or "0.0.0.0"  # When listing on POD network.
    run_ssh_commands(
        host=server_vm.ssh_exec, commands=[shlex.split(f"iperf3 -D -sB {_listen_ip}")]
    )
    iperf_data = run_ssh_commands(
        host=client_vm.ssh_exec,
        commands=[shlex.split(f"iperf3 -c {target_ip or listen_ip} -t 5 -J")],
    )[0]
    iperf_json = json.loads(iperf_data)
    sum_sent = iperf_json.get("end").get("sum_sent")
    bits_per_second = int(sum_sent.get("bits_per_second"))
    return float(bitmath.Byte(bits_per_second).GiB)


def assert_ssh_alive(ssh_vm, src_ip):
    """
    Check the ssh process is alive

    Args:
        ssh_vm (VirtualMachine): VM to ssh, this is the dst VM of run_ssh_in_background().
        src_ip (str): The IP of the src VM, this is the IP of the src VM of run_ssh_in_background().

    Raises:
        TimeoutExpiredError: When ssh process is not alive.
    """
    sampler = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=run_ssh_commands,
        host=ssh_vm.ssh_exec,
        commands=[shlex.split("sudo netstat -tulpan | grep ssh")],
    )
    try:
        for sample in sampler:
            if sample:
                for line in sample:
                    if src_ip in line and "ESTABLISHED" in line:
                        LOGGER.info(
                            f"SSH connection from {src_ip} to {ssh_vm.name} is alive"
                        )
                        return
    except TimeoutExpiredError:
        LOGGER.error(f"SSH connection from {src_ip} is not alive")
        raise


def run_ssh_in_background(nad, src_vm, dst_vm, dst_vm_user, dst_vm_password):
    """
    Start ssh connection to the vm
    """
    dst_ip = get_vmi_ip_v4_by_name(vm=dst_vm, name=nad.name)
    src_ip = str(get_vmi_ip_v4_by_name(vm=src_vm, name=nad.name))
    LOGGER.info(f"Start ssh connection to {dst_vm.name} from {src_vm.name}")
    run_ssh_commands(
        host=src_vm.ssh_exec,
        commands=[
            shlex.split(
                f"sshpass -p {dst_vm_password} ssh -o 'StrictHostKeyChecking no' "
                f"{dst_vm_user}@{dst_ip} 'sleep 99999' &>1 &"
            )
        ],
    )

    assert_ssh_alive(ssh_vm=dst_vm, src_ip=src_ip)


def assert_nncp_successfully_configured(nncp):
    successfully_configured = nncp.Conditions.Reason.SUCCESSFULLY_CONFIGURED
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=1,
        func=lambda: nncp.status,
    )
    try:
        for sample in sampler:
            if sample == successfully_configured:
                return

    except TimeoutExpiredError:
        LOGGER.error(f"{nncp.name} is not {successfully_configured}.")
        raise


def authentication_request(vm, expected_output, **kwargs):
    """
    Return server response to a request sent from VM console. This request allows testing client authentication.

    Args:
        vm (VirtualMachine): VM that will be used for console connection
        expected_output (str): The expected response from the server

    Kwargs: ( Used to allow passing args from wait_service_mesh_components_convergence in service_mesh/conftest)
        service (str): target svc dns name

    Returns:
        str: Server response
    """
    return verify_console_command_output(
        vm=vm,
        command=f"curl http://{kwargs['service']}:{SERVICE_MESH_PORT}/ip",
        expected_output=expected_output,
    )


def assert_service_mesh_request(expected_output, request_response):
    assert expected_output in request_response, (
        "Server response error."
        f"Expected output - {expected_output}"
        f"received - {request_response}"
    )


def assert_authentication_request(vm, service):
    expected_output = "127.0.0.1"
    request_response = authentication_request(
        vm=vm,
        service=service,
        expected_output=expected_output,
    )
    assert_service_mesh_request(
        expected_output=expected_output, request_response=request_response
    )


def verify_console_command_output(
    vm,
    command,
    expected_output,
    timeout=TIMEOUT_1MIN,
    console_impl=console.Cirros,
):
    """
    Run a list of commands inside a VM and check for expected output.
    """
    with console_impl(vm=vm) as vmc:
        LOGGER.info(f"Execute {command} on {vm.name}")
        try:
            vmc.sendline(command)
            vmc.expect(expected_output, timeout=timeout)
            return expected_output
        except pexpect.exceptions.TIMEOUT:
            return vmc.before.decode("utf-8")
