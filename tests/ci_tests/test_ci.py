import pytest
from pytest_testconfig import config as py_config

from utilities.constants import Images
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


# flake8: noqa: PID
pytestmark = pytest.mark.ci


@pytest.fixture(scope="session")
def skip_if_not_ovn_cluster(ovn_kubernetes_cluster):
    if not ovn_kubernetes_cluster:
        pytest.skip("Test can run only on cluster with OVN network type")


def test_ci_container_disk_vm(admin_client, namespace):
    name = "ci-container-disk-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)


def test_schedulable_nodes(schedulable_nodes):
    return


def test_masters(masters):
    return


def test_utility_daemonset(utility_daemonset):
    return


def test_utility_pods(utility_pods):
    return


def test_node_physical_nics(node_physical_nics):
    return


def test_nodes_active_nics(nodes_active_nics):
    return


def test_multi_nics_nodes(multi_nics_nodes):
    return


def test_workers_type(workers_type):
    return


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        (
            {
                "dv_name": "ci-cirros-dv",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            }
        )
    ],
    indirect=True,
)
def test_data_volume_scope_function(data_volume_scope_function):
    return


def test_nodes_common_cpu_model(nodes_common_cpu_model):
    return


def test_default_sc(default_sc):
    return


def test_hyperconverged_resource(hyperconverged_resource_scope_function):
    return


def test_kubevirt_hyperconverged_spec(kubevirt_hyperconverged_spec_scope_function):
    return


def test_network_addons_config(network_addons_config_scope_session):
    return


def test_cluster_storage_classes(cluster_storage_classes):
    return


def test_cnv_pods(cnv_pods):
    return
