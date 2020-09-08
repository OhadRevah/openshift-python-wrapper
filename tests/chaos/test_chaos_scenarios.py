import pytest
from tests.chaos.utils import BackgroundLoop, ChaosScenario
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture()
def migrate_loop_vm(namespace, unprivileged_client):
    name = "migrate-loop-vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start()
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def restart_loop_vm(namespace, unprivileged_client):
    name = "restart-loop-vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start()
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.chaos
@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("etcd", marks=pytest.mark.polarion("CNV-4407")),
        pytest.param("openshift-apiserver", marks=pytest.mark.polarion("CNV-4408")),
        pytest.param("virt-api", marks=pytest.mark.polarion("CNV-4409")),
    ],
)
def test_chaos_scenario(scenario, admin_client, migrate_loop_vm, restart_loop_vm):
    with ChaosScenario(
        client=admin_client,
        scenario=scenario,
        loops=[
            BackgroundLoop(
                action=ChaosScenario.LoopAction.MIGRATE,
                vms=[migrate_loop_vm],
            ),
            BackgroundLoop(
                action=ChaosScenario.LoopAction.RESTART,
                vms=[restart_loop_vm],
            ),
        ],
    ) as scenario:
        assert scenario.run_scenario()

    for vm in [restart_loop_vm, migrate_loop_vm]:
        vm.vmi.wait_until_running()
