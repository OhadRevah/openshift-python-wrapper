
import pytest
from autologs.autologs import generate_logs
from tests.test_utils import wait_for_vm_interfaces

from resources.node import Node
from resources.pod import Pod
from resources.resource import Resource
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_instance import VirtualMachineInstance
from utilities import types, utils

from . import config


@pytest.fixture(scope='module')
def get_ovs_cni_pods(request):
    """
    Get ovs-cni pods names
    """
    pytest.privileged_pods = [i for i in Pod().list(get_names=True) if i.startswith("ovs-cni")]
    if pytest.privileged_pods:
        pytest.privileged_pod_container = config.OVS_CNI_CONTAINER
        pytest.privileged_pods_ns = config.KUBE_SYSTEM_NS
        pytest.ovs_del_br = config.OVS_VSCTL_DEL_BR
        pytest.ovs_add_br = config.OVS_VSCTL_ADD_BR
        pytest.ovs_add_port = config.OVS_VSCTL_ADD_PORT
    else:
        pytest.privileged_pod_container = "privileged-test-pod"
        pytest.privileged_pods_ns = config.NETWORK_NS
        pytest.ovs_del_br = f"{config.OVS_VSCTL} del-br"
        pytest.ovs_add_br = f"{config.OVS_VSCTL} add-br"
        pytest.ovs_add_port = f"{config.OVS_VSCTL} add-port"


@pytest.fixture(scope='module')
def create_privileged_user(request):
    """
    Create privileged service account
    """
    if pytest.privileged_pods:
        return

    def fin():
        """
        Remove privileged service account
        """
        utils.run_oc_command(
            command="delete serviceaccount privileged-test-user",
            namespace=config.NETWORK_NS
        )
    request.addfinalizer(fin)

    assert utils.run_oc_command(
        command="create serviceaccount privileged-test-user",
        namespace=config.NETWORK_NS
    )[0]
    assert utils.run_oc_command(
        command="adm policy add-scc-to-user privileged -z privileged-test-user",
        namespace=config.NETWORK_NS
    )[0]


@pytest.fixture(scope='module')
def create_privileged_pods(request):
    """
    Create privileged pods
    """
    if pytest.privileged_pods:
        return

    pods_yaml = "tests/manifests/privileged-pod-ds.yml"
    resource = Resource(namespace=config.NETWORK_NS)

    def fin():
        resource.delete(yaml_file=pods_yaml, wait=True)
    request.addfinalizer(fin)

    compute_nodes = Node().list(get_names=True, label_selector="node-role.kubernetes.io/compute=true")
    assert resource.create(yaml_file=pods_yaml)
    wait_for_pods_to_match_compute_nodes_number(number_of_nodes=len(compute_nodes))
    privileged_pods = Pod().list(get_names=True, label_selector="app=privileged-test-pod")
    for idx, pod in enumerate(privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        assert pod_object.wait_for_status(status=types.RUNNING)
    pytest.privileged_pods = privileged_pods


@pytest.fixture(scope='module')
def create_networks_from_yaml(request):
    """
    Create network CRDs from yaml files
    """
    resource = Resource(namespace=config.NETWORK_NS)
    yamls = (config.OVS_VLAN_YAML, config.OVS_BOND_YAML, config.OVS_VLAN_YAML_VXLAN)

    def fin():
        """
        Remove network CRDs
        """
        for yaml_ in yamls:
            Resource().delete(yaml_file=yaml_, wait=True)
    request.addfinalizer(fin)

    for yaml_ in yamls:
        resource.create(yaml_file=yaml_, wait=True)


@pytest.fixture(scope='module')
def get_node_internal_ip(request):
    """
    Get nodes internal IPs
    """
    compute_nodes = Node().list(get_names=True, label_selector="node-role.kubernetes.io/compute=true")
    for node in compute_nodes:
        node_obj = Node(name=node)
        node_info = node_obj.get()
        for addr in node_info.status.addresses:
            if addr.type == "InternalIP":
                pytest.nodes_network_info[node] = addr.address
                break
    assert len(pytest.nodes_network_info.keys()) == len(compute_nodes)


@pytest.fixture(scope='module')
def is_bare_metal():
    """
    Check if setup is on bare-metal
    """
    for idx, pod in enumerate(pytest.privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_container = pytest.privileged_pod_container
        pytest.active_node_nics[pod] = []
        assert pod_object.wait_for_status(status=types.RUNNING)
        err, nics = pod_object.run_command(command=config.GET_NICS_CMD, container=pod_container)
        assert err
        nics = nics.splitlines()
        err, default_gw = pod_object.run_command(command="ip route show default", container=pod_container)
        assert err
        for nic in nics:
            err, nic_state = pod_object.run_command(
                command=f"cat /sys/class/net/{nic}/operstate", container=pod_container
            )
            assert err
            if nic_state.strip() == "up":
                if nic in [i for i in default_gw.splitlines() if 'default' in i][0]:
                    continue

                pytest.active_node_nics[pod].append(nic)

                err, driver = pod_object.run_command(
                    command=config.CHECK_NIC_DRIVER_CMD.format(nic=nic), container=pod_container
                )
                assert err
                pytest.real_nics_env = driver.strip() != "virtio_net"


@pytest.fixture(scope='module')
def is_bond_supported():
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    pytest.bond_support_env = max([len(pytest.active_node_nics[i]) for i in pytest.privileged_pods]) > 2


@pytest.fixture(scope='module')
def create_ovs_bridges_real_nics(request):
    """
    Create needed OVS bridges when setup is bare-metal
    """
    if not pytest.real_nics_env:
        return

    real_nics_bridge = config.BRIDGE_NAME_REAL_NICS

    def fin():
        """
        Remove created OVS bridges
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
            pod_container = pytest.privileged_pod_container
            pod_object.run_command(command=f"{pytest.ovs_del_br} {real_nics_bridge}", container=pod_container)
    request.addfinalizer(fin)

    for idx, pod in enumerate(pytest.privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_name = pod
        pod_container = pytest.privileged_pod_container
        if pytest.real_nics_env:
            assert pod_object.run_command(
                command=f"{pytest.ovs_add_br} {real_nics_bridge}", container=pod_container
            )[0]

            assert pod_object.run_command(
                command=(
                    f"{pytest.ovs_add_port} "
                    f"{real_nics_bridge} "
                    f"{pytest.active_node_nics[pod_name][0]}"
                ), container=pod_container
            )[0]


@pytest.fixture(scope='module')
def create_ovs_bridge_on_vxlan(request):
    """
    Create needed OVS bridges when setup is not bare-metal
    """
    if pytest.real_nics_env:
        return

    bridge_name_vxlan = config.BRIDGE_NAME_VXLAN
    vxlan_port = "ovs_novlan_port"

    def fin():
        """
        Remove created OVS bridges
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
            pod_container = pytest.privileged_pod_container
            pod_object.run_command(command=f"{pytest.ovs_del_br} {bridge_name_vxlan}", container=pod_container)
    request.addfinalizer(fin)

    for idx, pod in enumerate(pytest.privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_container = pytest.privileged_pod_container
        node_name = pod_object.node()
        assert pod_object.run_command(
            command=f"{pytest.ovs_add_br} {bridge_name_vxlan}", container=pod_container
        )[0]
        for name, ip in pytest.nodes_network_info.items():
            if name != node_name:
                assert pod_object.run_command(
                    command=(
                        f"{pytest.ovs_add_port} {bridge_name_vxlan} vxlan -- "
                        f"set Interface vxlan type=vxlan options:remote_ip={ip}"
                    ), container=pod_container
                )[0]
                break

        assert pod_object.run_command(
            command=(
                f"{pytest.ovs_add_port} {bridge_name_vxlan} {vxlan_port} -- "
                f"set Interface {vxlan_port} type=internal"
            ), container=pod_container
        )[0]

        assert pod_object.run_command(
            command=f"ip addr add {config.OVS_NODES_IPS[idx]} dev {vxlan_port}", container=pod_container
        )[0]


@pytest.fixture(scope='module')
def create_bond(request):
    """
    Create BOND if setup support BOND
    """
    bond_name = config.BOND_NAME
    bond_bridge = config.BOND_BRIDGE

    if not pytest.bond_support_env:
        return

    def fin():
        """
        Remove created BOND
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
            pod_container = pytest.privileged_pod_container
            pod_object.run_command(command=f"ip link del {bond_name}", container=pod_container)
    request.addfinalizer(fin)

    bond_commands = [
        f"ip link add {bond_name} type bond", f"ip link set {bond_name} type bond miimon 100 mode active-backup"
    ]
    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_name = pod
        pod_container = pytest.privileged_pod_container
        for cmd in bond_commands:
            assert pod_object.run_command(command=cmd, container=pod_container)[0]

        for nic in pytest.active_node_nics[pod_name][1:3]:
            assert pod_object.run_command(
                command=config.IP_LINK_INTERFACE_DOWN.format(interface=nic), container=pod_container
            )[0]

            assert pod_object.run_command(
                command=f"ip link set {nic} master {bond_name}", container=pod_container
            )[0]

            assert pod_object.run_command(
                command=config.IP_LINK_INTERFACE_UP.format(interface=nic), container=pod_container
            )[0]

        assert pod_object.run_command(
            command=config.IP_LINK_INTERFACE_UP.format(interface=bond_name), container=pod_container
        )[0]

        res, out = pod_object.run_command(command=f"ip link show {bond_name}", container=pod_container)

        assert res
        assert "state UP" in out

        assert pod_object.run_command(
            command=f"{pytest.ovs_add_br} {bond_bridge}", container=pod_container
        )[0]

        assert pod_object.run_command(
            command=f"{pytest.ovs_add_port} {bond_bridge} {bond_name}", container=pod_container
        )[0]


@pytest.fixture(scope='module')
def create_vms(request):
    """
    Create VMs
    """
    vms = config.VMS_LIST

    def fin():
        """
        Remove created VMs if exists (TestVethRemovedAfterVmsDeleted should remove them)
        """
        for vm in vms:
            vm_object = VirtualMachine(name=vm, namespace=config.NETWORK_NS)
            if vm_object.get():
                vm_object.delete(wait=True)
    request.addfinalizer(fin)

    for vm in vms:
        vm_object = VirtualMachine(name=vm, namespace=config.NETWORK_NS)
        network = "ovs-vlan-net" if pytest.real_nics_env else "ovs-vlan-net-vxlan"
        json_out = utils.get_json_from_template(file_=config.VM_YAML_TEMPLATE, NAME=vm, MULTUS_NETWORK=network)
        spec = json_out.get('spec').get('template').get('spec')
        volumes = spec.get('volumes')
        cloud_init = [i for i in volumes if 'cloudInitNoCloud' in i][0]
        cloud_init_data = volumes.pop(volumes.index(cloud_init))
        cloud_init_user_data = cloud_init_data.get('cloudInitNoCloud').get('userData')
        cloud_init_user_data += (
            "\nruncmd:\n"
            "  - nmcli con add type ethernet con-name eth1 ifname eth1\n"
            "  - nmcli con mod eth1 ipv4.addresses {ip}/24 ipv4.method manual\n"
            "  - systemctl start qemu-guest-agent\n".format(ip=config.VMS.get(vm).get("ovs_ip"))
        )
        if not pytest.real_nics_env:
            cloud_init_user_data += "  - ip link set mtu 1450 eth1\n"

        if pytest.bond_support_env:
            interfaces = spec.get('domain').get('devices').get('interfaces')
            networks = spec.get('networks')
            bond_bridge_interface = {'bridge': {}, 'name': 'ovs-net-bond'}
            bond_bridge_network = {'multus': {'networkName': 'ovs-net-bond'}, 'name': 'ovs-net-bond'}
            interfaces.append(bond_bridge_interface)
            networks.append(bond_bridge_network)
            cloud_init_user_data += (
                "  - nmcli con add type ethernet con-name eth1 ifname eth2\n"
                "  - nmcli con mod eth2 ipv4.addresses {ip}/24 ipv4.method manual\n".format(
                    ip=config.VMS.get(vm).get("bond_ip")
                )
            )
            spec['domain']['devices']['interfaces'] = interfaces
            spec['networks'] = networks

        cloud_init_data['cloudInitNoCloud']['userData'] = cloud_init_user_data
        volumes.append(cloud_init_data)
        spec['volumes'] = volumes
        json_out['spec']['template']['spec'] = spec
        assert vm_object.create(resource_dict=json_out, wait=True)


@pytest.fixture(scope='module')
def wait_for_vms_status(request):
    """
    Wait until VMs report guest agant data
    """
    for vmi in config.VMS_LIST:
        vmi_object = VirtualMachineInstance(name=vmi, namespace=config.NETWORK_NS)
        assert vmi_object.wait_for_status(status=types.RUNNING)
        wait_for_vm_interfaces(vmi=vmi_object)
        vmi_data = vmi_object.get()
        ifcs = vmi_data.get('status', {}).get('interfaces', [])
        active_ifcs = [i.get('ipAddress') for i in ifcs if i.get('interfaceName') == "eth0"]
        config.VMS[vmi]["pod_ip"] = active_ifcs[0].split("/")[0]


@pytest.fixture(scope='module', autouse=True)
def prepare_env(
    request,
    get_ovs_cni_pods,
    create_privileged_user,
    create_privileged_pods,
    create_networks_from_yaml,
    get_node_internal_ip,
    is_bare_metal,
    is_bond_supported,
    create_ovs_bridges_real_nics,
    create_ovs_bridge_on_vxlan,
    create_bond,
    create_vms,
    wait_for_vms_status
):
    """
    Prepare env for tests
    """
    pass


@generate_logs()
def wait_for_pods_to_match_compute_nodes_number(number_of_nodes):
    """
    Wait for pods to be created from DaemonSet

    Args:
        number_of_nodes (int): Number of nodes to match for.

    Returns:
        bool: True if Pods created.

    Raises:
        TimeoutExpiredError: After timeout reached.

    """
    sampler = utils.TimeoutSampler(
        timeout=30, sleep=1, func=Pod().list, get_names=True, label_selector="app=privileged-test-pod"
    )
    for sample in sampler:
        if len(sample) == number_of_nodes:
            return True
