import pytest

from resources.namespace import Namespace
from resources.service import Service
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.network.utils import vm_run_commands
from tests.utils import FedoraVirtualMachine, wait_for_vm_interfaces


def http_port_accessible(vm, server_ip):
    vm_run_commands(vm, [f"curl --head {server_ip}:80 --connect-timeout 5"], timeout=10)


class VirtualMachineMasquerade(FedoraVirtualMachine):
    def __init__(self, name, namespace):
        super().__init__(name=name, namespace=namespace)

    def _to_dict(self):
        res = super()._to_dict()
        vm_interfaces = res["spec"]["template"]["spec"]["domain"]["devices"][
            "interfaces"
        ]
        for iface in vm_interfaces:
            if "masquerade" in iface.keys():
                iface["ports"] = [{"name": "http80", "port": 80, "protocol": "TCP"}]
        return res


class HTTPService(Service):
    def __init__(self, name, namespace, vmi):
        super().__init__(name=name, namespace=namespace)
        self._vmi = vmi

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "ports": [{"port": 80, "protocol": "TCP", "targetPort": 80}],
            "selector": {"special": self._vmi.name},
            "sessionAffinity": "None",
            "type": "ClusterIP",
        }
        return res


@pytest.fixture(scope="module")
def namespace():
    with Namespace(name="network-migration-test") as ns:
        yield ns


@pytest.fixture(scope="module")
def vma(namespace):
    with VirtualMachineMasquerade(namespace=namespace.name, name="vma") as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def vmb(namespace):
    with FedoraVirtualMachine(namespace=namespace.name, name="vmb") as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vma.vmi)
    yield vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmb.vmi)
    yield vmb


@pytest.fixture()
def http_service(namespace, network_utility_pods, vma, vmb, running_vma, running_vmb):
    with HTTPService(
        name="http-masquerade-migration", namespace=namespace.name, vmi=vma
    ) as svc:
        # Check that http service on port 80 can be accessed by cluster IP
        # before vmi migration.
        http_port_accessible(vmb, vma.vmi.virt_launcher_pod.instance.status.podIP)
        yield svc


@pytest.mark.polation("CNV-2061")
def test_migration_with_masquerade(
    default_client,
    skip_when_one_node,
    network_utility_pods,
    vma,
    vmb,
    running_vma,
    running_vmb,
    http_service,
):
    vmi_node_before_migration = vma.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="masquerade-migration", namespace=vma.namespace, vmi=vma.vmi
    ) as mig:
        mig.wait_for_status(status="Succeeded", timeout=720)

        assert vma.vmi.instance.status.nodeName != vmi_node_before_migration
        assert vma.vmi.instance.status.migrationState.completed
        http_port_accessible(vmb, vma.vmi.virt_launcher_pod.instance.status.podIP)
