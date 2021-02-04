"""
Report VM IP
"""

import pytest
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration

from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


def assert_ip_mismatch(vm):
    sampler = TimeoutSampler(
        timeout=10,
        sleep=1,
        func=lambda: vm.interface_ip(interface="eth0") == vm.virt_launcher_pod.ip,
    )
    for sample in sampler:
        if sample:
            return


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
    assert_ip_mismatch(vm=report_masquerade_ip_vm)


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

    assert_ip_mismatch(vm=report_masquerade_ip_vm)
