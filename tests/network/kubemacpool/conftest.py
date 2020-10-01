import pytest
import tests.network.utils as network_utils
import utilities.network
from resources.daemonset import DaemonSet
from resources.deployment import Deployment
from resources.namespace import Namespace
from resources.resource import ResourceEditor
from tests.network.utils import running_vmi
from utilities.infra import create_ns
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)

from . import utils as kmp_utils


@pytest.fixture(scope="module")
def bridge_device(
    skip_if_no_multinic_nodes,
    nodes_available_nics,
    utility_pods,
    schedulable_nodes,
):
    with network_utils.network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name="kubemacpool",
        interface_name="br1test",
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[
            utilities.network.get_hosts_common_ports(
                nodes_available_nics=nodes_available_nics
            )[1]
        ],
    ) as dev:
        yield dev


@pytest.fixture(scope="module")
def manual_mac_nad(namespace, bridge_device):
    with utilities.network.network_nad(
        nad_type=bridge_device.bridge_type,
        nad_name="manual-mac-nad",
        interface_name=bridge_device.bridge_name,
        namespace=namespace,
    ) as manual_mac_nad:
        yield manual_mac_nad


@pytest.fixture(scope="module")
def automatic_mac_nad(namespace, bridge_device):
    with utilities.network.network_nad(
        nad_type=bridge_device.bridge_type,
        nad_name="automatic-mac-nad",
        interface_name=bridge_device.bridge_name,
        namespace=namespace,
    ) as automatic_mac_nad:
        yield automatic_mac_nad


@pytest.fixture(scope="module")
def manual_mac_out_of_pool_nad(namespace, bridge_device):
    with utilities.network.network_nad(
        nad_type=bridge_device.bridge_type,
        nad_name="manual-out-pool-mac-nad",
        interface_name=bridge_device.bridge_name,
        namespace=namespace,
        tuning=True,
    ) as manual_mac_out_pool_nad:
        yield manual_mac_out_pool_nad


@pytest.fixture(scope="module")
def automatic_mac_tuning_net_nad(namespace, bridge_device):
    with utilities.network.network_nad(
        nad_type=bridge_device.bridge_type,
        nad_name="automatic-mac-tun-net-nad",
        interface_name=bridge_device.bridge_name,
        namespace=namespace,
        tuning=True,
    ) as automatic_mac_tuning_net_nad:
        yield automatic_mac_tuning_net_nad


@pytest.fixture(scope="class")
def opted_out_ns_nad(opted_out_ns, bridge_device):
    with utilities.network.network_nad(
        nad_type=bridge_device.bridge_type,
        nad_name=f"{opted_out_ns.name}-nad",
        interface_name=bridge_device.bridge_name,
        namespace=opted_out_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def wrong_label_ns_nad(wrong_label_ns, bridge_device):
    with utilities.network.network_nad(
        nad_type=bridge_device.bridge_type,
        nad_name=f"{wrong_label_ns.name}-nad",
        interface_name=bridge_device.bridge_name,
        namespace=wrong_label_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def all_nads(
    manual_mac_nad,
    automatic_mac_nad,
    manual_mac_out_of_pool_nad,
    automatic_mac_tuning_net_nad,
):
    return [
        manual_mac_nad.name,
        automatic_mac_nad.name,
        manual_mac_out_of_pool_nad.name,
        automatic_mac_tuning_net_nad.name,
    ]


@pytest.fixture(scope="class")
def vm_a(
    namespace,
    all_nads,
    bridge_device,
    mac_pool,
    unprivileged_client,
):
    requested_network_config = kmp_utils.vm_network_config(
        mac_pool=mac_pool, all_nads=all_nads, end_ip=1, mac_uid="1"
    )
    yield from kmp_utils.create_vm(
        name="vm-fedora-a",
        iface_config=requested_network_config,
        namespace=namespace,
        client=unprivileged_client,
        mac_pool=mac_pool,
    )


@pytest.fixture(scope="class")
def vm_b(
    namespace,
    all_nads,
    bridge_device,
    mac_pool,
    unprivileged_client,
):
    requested_network_config = kmp_utils.vm_network_config(
        mac_pool=mac_pool, all_nads=all_nads, end_ip=2, mac_uid="2"
    )
    yield from kmp_utils.create_vm(
        name="vm-fedora-b",
        iface_config=requested_network_config,
        namespace=namespace,
        client=unprivileged_client,
        mac_pool=mac_pool,
    )


@pytest.fixture(scope="class")
def started_vmi_a(vm_a):
    return running_vmi(vm=vm_a)


@pytest.fixture(scope="class")
def started_vmi_b(vm_b):
    return running_vmi(vm=vm_b)


@pytest.fixture(scope="class")
def running_vm_a(vm_a, started_vmi_a):
    wait_for_vm_interfaces(vmi=started_vmi_a)
    return vm_a


@pytest.fixture(scope="class")
def running_vm_b(vm_b, started_vmi_b):
    wait_for_vm_interfaces(vmi=started_vmi_b)
    return vm_b


@pytest.fixture(scope="function")
def restarted_vmi_a(vm_a):
    vm_a.stop(wait=True)
    return running_vmi(vm=vm_a)


@pytest.fixture(scope="function")
def restarted_vmi_b(vm_b):
    vm_b.stop(wait=True)
    return running_vmi(vm=vm_b)


@pytest.fixture(scope="class")
def opted_out_ns_vm(opted_out_ns, opted_out_ns_nad, mac_pool):
    networks = {opted_out_ns_nad.name: opted_out_ns_nad.name}
    name = f"{opted_out_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=opted_out_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name=name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def wrong_label_ns_vm(wrong_label_ns, wrong_label_ns_nad, mac_pool):
    networks = {wrong_label_ns_nad.name: wrong_label_ns_nad.name}
    name = f"{wrong_label_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=wrong_label_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name=name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def opted_out_ns():
    yield from create_ns(name="kmp-opted-out")


@pytest.fixture(scope="class")
def wrong_label_ns(kmp_vm_label):
    kmp_vm_label["mutatevirtualmachines.kubemacpool.io"] += "-wrong-label"
    yield from create_ns(name="kmp-wrong-label", kmp_vm_label=kmp_vm_label)


@pytest.fixture()
def ovn_ns():
    return Namespace(name="openshift-ovn-kubernetes")


@pytest.fixture()
def kmp_down(cnao_down, kmp_deployment):
    with ResourceEditor(patches={kmp_deployment: {"spec": {"replicas": 0}}}):
        kmp_deployment.wait_until_no_replicas()
        yield


@pytest.fixture()
def cnao_down(cnao_deployment):
    with ResourceEditor(patches={cnao_deployment: {"spec": {"replicas": 0}}}):
        cnao_deployment.wait_until_no_replicas()
        yield


@pytest.fixture(scope="module")
def cnao_deployment(hco_namespace):
    return Deployment(
        namespace=hco_namespace.name, name="cluster-network-addons-operator"
    )


@pytest.fixture(scope="module")
def kmp_deployment(hco_namespace):
    return Deployment(
        namespace=hco_namespace.name, name="kubemacpool-mac-controller-manager"
    )


@pytest.fixture()
def bad_kmp_containers(kmp_deployment):
    containers = kmp_deployment.instance.to_dict()["spec"]["template"]["spec"][
        "containers"
    ]
    for container in containers:
        if container["name"] == "manager":
            container["command"] = ["false"]
            return containers


@pytest.fixture()
def kmp_crash_loop(
    admin_client, hco_namespace, cnao_down, kmp_deployment, bad_kmp_containers
):
    with ResourceEditor(
        patches={
            kmp_deployment: {
                "spec": {"template": {"spec": {"containers": bad_kmp_containers}}}
            }
        }
    ):
        kmp_utils.wait_for_pods_deletion(
            pods=kmp_utils.get_pods(
                dyn_client=admin_client,
                namespace=hco_namespace,
                label=kmp_utils.KMP_PODS_LABEL,
            )
        )
        kmp_utils.wait_for_kmp_pods_creation(
            dyn_client=admin_client,
            namespace=hco_namespace,
            replicas=kmp_deployment.instance.spec.replicas,
        )
        kmp_utils.wait_for_kmp_pods_to_be_in_crashloop(
            dyn_client=admin_client,
            namespace=hco_namespace,
        )
        yield


@pytest.fixture()
def skip_if_no_ovn(ovn_ns):
    if not ovn_ns.exists:
        pytest.skip(
            msg="Test only works on cluster with openshift-ovn-kubernetes deployed"
        )


@pytest.fixture()
def ovnkube_node_daemonset(ovn_ns):
    return DaemonSet(name="ovnkube-node", namespace=ovn_ns.name)


@pytest.fixture()
def deleted_ovnkube_node_pod(admin_client, ovn_ns):
    pods = kmp_utils.get_pods(
        dyn_client=admin_client, namespace=ovn_ns, label="app=ovnkube-node"
    )
    assert pods, "No ovnkube-node pods were found"
    pods[0].delete(wait=True)
