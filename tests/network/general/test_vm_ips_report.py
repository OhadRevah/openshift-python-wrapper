"""
Report VM IP
"""

import pytest
from resources.virtual_machine import VirtualMachineInstanceMigration

from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module")
def report_masquerade_ip_vm(unprivileged_client, namespace):
    name = "report-masquerade-ip-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vmi = vm.vmi
        vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vmi)
        yield vmi


@pytest.mark.polarion("CNV-4455")
def test_report_masquerade_ip(report_masquerade_ip_vm):
    assert (
        report_masquerade_ip_vm.interface_ip(interface="eth0")
        == report_masquerade_ip_vm.virt_launcher_pod.ip
    )


@pytest.mark.bugzilla(
    1686208, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-4153")
def test_report_masquerade_ip_after_migration(report_masquerade_ip_vm):
    src_node = report_masquerade_ip_vm.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="report-masquerade-ip-migration",
        namespace=report_masquerade_ip_vm.namespace,
        vmi=report_masquerade_ip_vm,
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert report_masquerade_ip_vm.instance.status.nodeName != src_node

    assert (
        report_masquerade_ip_vm.interface_ip(interface="eth0")
        == report_masquerade_ip_vm.virt_launcher_pod.ip
    )
