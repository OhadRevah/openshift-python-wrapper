import json
import logging
import shlex

import bitmath
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_2MIN
from utilities.infra import run_ssh_commands
from utilities.network import get_vmi_ip_v4_by_name, ping


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
                        LOGGER.info(f"SSH connection from {src_ip} is alive")
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
