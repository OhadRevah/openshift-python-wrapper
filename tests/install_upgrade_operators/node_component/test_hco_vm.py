import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.resource import ResourceEditor

from tests.install_upgrade_operators.node_component.utils import (
    NODE_PLACEMENT_INFRA,
    NODE_PLACEMENT_WORKLOADS,
)
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_console,
    wait_for_vm_interfaces,
)


@pytest.fixture()
def hco_vm(unprivileged_client, namespace):
    name = "hco-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        running=True,
    ) as vm:
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        wait_for_console(vm=vm, console_impl=console.Fedora)
        yield vm
        vm.stop(wait=True)


@pytest.mark.parametrize(
    "hyperconverged_with_node_placement",
    [
        pytest.param(
            {"infra": NODE_PLACEMENT_INFRA, "workloads": NODE_PLACEMENT_WORKLOADS},
            marks=(
                pytest.mark.polarion("CNV-5715"),
                pytest.mark.bugzilla(
                    1917380, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        )
    ],
    indirect=True,
)
def test_remove_workload_label_from_node_while_vm_running(
    node_placement_labels, hyperconverged_with_node_placement, hco_vm
):
    with pytest.raises(
        ApiException
    ):  # TODO: replace with specific exception after BZ 1917380
        with ResourceEditor(
            patches={hco_vm.vmi.node: {"metadata": {"labels": {"work-comp": None}}}}
        ):
            pytest.fail("Workload label removed while VM is running")