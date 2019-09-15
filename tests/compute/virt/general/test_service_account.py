"""
Check VM with Service Account
"""

import pytest
from kubernetes.client.rest import ApiException
from resources.namespace import Namespace
from resources.service_account import ServiceAccount
from tests.utils import VirtualMachineForTests
from utilities import console


@pytest.fixture(scope="module", autouse=True)
def sa_namespace():
    with Namespace(name="service-account-test") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.fixture(scope="module")
def service_account(sa_namespace):
    with ServiceAccount(name="sa-test", namespace=sa_namespace.name) as sa:
        yield sa


@pytest.fixture()
def vm_vmi(sa_namespace, service_account):
    with VirtualMachineForTests(
        name="service-account-vm",
        namespace=sa_namespace.name,
        service_accounts=[service_account.name],
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm.vmi


@pytest.mark.polarion("CNV-1000")
def test_vm_with_specified_service_account(vm_vmi):
    """
    Verifies VM with specified ServiceAccount
    """

    pod_sa = vm_vmi.virt_launcher_pod.execute(
        command=["cat", f"/var/run/secrets/kubernetes.io/serviceaccount/namespace"],
        container="compute",
    )
    assert pod_sa == vm_vmi.namespace, "ServiceAccount should be attached to the POD"

    # Verifies that ServiceAccount is attached to VMI
    with console.Fedora(vm_vmi) as vm_console:
        vm_console.sendline("sudo su -")
        vm_console.expect("#")
        vm_console.sendline("mount /dev/sda /mnt")
        vm_console.sendline("echo rc==$?==")
        vm_console.expect("rc==0==")
        vm_console.sendline("cat /mnt/namespace")
        vm_console.expect(vm_vmi.namespace)
        vm_console.sendline("exit")
        vm_console.expect("$")


@pytest.mark.polarion("CNV-1001")
def test_vm_with_2_service_accounts(sa_namespace):
    """
    Negative: Verifies that VM with 2 ServiceAccounts can't be created
    """
    with pytest.raises(ApiException, match=r".* must have max one serviceAccount .*"):
        with VirtualMachineForTests(
            name="vm-with-2-sa",
            namespace=sa_namespace.name,
            service_accounts=["sa-1", "sa-2"],
        ):
            return
