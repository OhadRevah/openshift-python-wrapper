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
def standard_scenario(scenario_name):
    with LitmusScenario(scenario=scenario_name, kind="standard") as scenario:
        yield scenario


@pytest.mark.chaos
@pytest.mark.parametrize(
    "scenario_name",
    [
        pytest.param("scenario01", marks=pytest.mark.polarion("CNV-5428")),
        pytest.param("scenario02", marks=pytest.mark.polarion("CNV-5429")),
        pytest.param("scenario03", marks=pytest.mark.polarion("CNV-5430")),
        pytest.param("scenario04", marks=pytest.mark.polarion("CNV-5431")),
        pytest.param("scenario05", marks=pytest.mark.polarion("CNV-5434")),
        pytest.param("scenario06", marks=pytest.mark.polarion("CNV-5435")),
        pytest.param("scenario07", marks=pytest.mark.polarion("CNV-5436")),
        pytest.param("scenario08", marks=pytest.mark.polarion("CNV-5629")),
        pytest.param("scenario09", marks=pytest.mark.polarion("CNV-5623")),
        pytest.param("scenario10", marks=pytest.mark.polarion("CNV-5439")),
        pytest.param("scenario11", marks=pytest.mark.polarion("CNV-5440")),
        pytest.param("scenario12", marks=pytest.mark.polarion("CNV-5438")),
        pytest.param("scenario13", marks=pytest.mark.polarion("CNV-5443")),
        pytest.param("scenario14", marks=pytest.mark.polarion("CNV-5667")),
    ],
)
def test_scenarios(scenario_name, standard_scenario, admin_client):
    standard_scenario.run_scenario()

    for engine in ChaosEngine.get(dyn_client=admin_client, namespace=scenario_name):
        assert engine.success, f"Scenario {scenario_name} failed"
