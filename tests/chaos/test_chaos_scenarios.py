import pytest
from resources.chaos_engine import ChaosEngine

from tests.chaos.utils import BackgroundLoop, ChaosScenario, LitmusScenario
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


@pytest.fixture()
def scenario(scenario_name):
    with LitmusScenario(scenario=scenario_name) as scenario:
        yield scenario


@pytest.mark.chaos
@pytest.mark.parametrize(
    "scenario_name",
    [
        pytest.param("scenario01", marks=pytest.mark.polarion("CNV-5428")),
        pytest.param("scenario02", marks=pytest.mark.polarion("CNV-5429")),
        pytest.param("scenario03", marks=pytest.mark.polarion("CNV-5430")),
        pytest.param("scenario04", marks=pytest.mark.polarion("CNV-5431")),
    ],
)
def test_scenarios(scenario_name, scenario, admin_client):
    scenario.run_scenario()

    for engine in ChaosEngine.get(dyn_client=admin_client, namespace=scenario_name):
        assert engine.success, f"Scenario {scenario_name} failed"
