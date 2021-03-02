"""
Check VM with Service Account
"""

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.service_account import ServiceAccount

from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
)


@pytest.fixture(scope="module")
def service_account(namespace):
    with ServiceAccount(name="sa-test", namespace=namespace.name) as sa:
        yield sa


@pytest.fixture()
def vm_vmi(namespace, service_account, unprivileged_client):
    name = "service-account-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        service_accounts=[service_account.name],
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
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
        command=["cat", "/var/run/secrets/kubernetes.io/serviceaccount/namespace"],
        container="compute",
    )
    assert pod_sa == vm_vmi.namespace, "ServiceAccount should be attached to the POD"

    # Verifies that ServiceAccount is attached to VMI
    with console.Fedora(vm=vm_vmi) as vm_console:
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
def test_vm_with_2_service_accounts(namespace):
    """
    Negative: Verifies that VM with 2 ServiceAccounts can't be created
    """
    name = "vm-with-2-sa"
    with pytest.raises(ApiException, match=r".* must have max one serviceAccount .*"):
        with VirtualMachineForTests(
            name=name,
            namespace=namespace.name,
            service_accounts=["sa-1", "sa-2"],
            body=fedora_vm_body(name=name),
            cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        ):
            return
