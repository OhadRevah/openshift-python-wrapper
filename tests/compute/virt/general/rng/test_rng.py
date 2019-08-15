"""
Test VM with RNG
"""

import pytest

from tests import utils as test_utils
from tests.utils import FedoraVirtualMachine
from utilities import console
from resources.namespace import Namespace


class FedoraVirtualMachineWithRNG(FedoraVirtualMachine):
    def __init__(self, name, namespace, interfaces=None, networks=None):
        super().__init__(
            name=name, namespace=namespace, interfaces=interfaces, networks=networks
        )

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"]["template"]["spec"]["domain"]["devices"].setdefault("rng", {})
        return res


@pytest.fixture(scope="module", autouse=True)
def rng_namespace():
    with Namespace(name="rng-test") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.fixture()
def rng_vm(default_client, rng_namespace):
    name = "vmi-with-rng"
    with FedoraVirtualMachineWithRNG(name=name, namespace=rng_namespace.name) as vm:
        vm.start(wait=True)
        assert test_utils.wait_for_vm_interfaces(vm.vmi)
        yield vm


@pytest.mark.polarion("CNV-791")
def test_vm_with_rng(rng_vm):
    """
    Test VM with RNG
     - check random device should be present
     - create random data with each device
    """
    with console.Console(vm=rng_vm) as vm_console:
        vm_console.sendline("cat /sys/devices/virtual/misc/hw_random/rng_current")
        vm_console.expect("virtio_rng.0", timeout=20)
        for device in ["random", "hwrng"]:
            vm_console.sendline(
                f"sudo dd count=10 bs=1024 if=/dev/{device} of=/tmp/{device}.txt"
            )
            vm_console.sendline(f"ls /tmp/{device}.txt | wc -l")
            vm_console.expect("1", timeout=20)
