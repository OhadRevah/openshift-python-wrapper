"""
Report VM IP
"""

import pytest
from ocp_resources.utils import TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachineInstanceMigration

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


def assert_ip_mismatch(vm):
    sampler = TimeoutSampler(
        wait_timeout=10,
        sleep=1,
        func=lambda: vm.interface_ip(interface="eth0") == vm.virt_launcher_pod.ip,
    )
    for sample in sampler:
        if sample:
            return


@pytest.fixture(scope="module")
def report_masquerade_ip_vmi(unprivileged_client, namespace):
    name = "report-masquerade-ip-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm, enable_ssh=False)
        yield vm.vmi


@pytest.mark.polarion("CNV-4455")
def test_report_masquerade_ip(report_masquerade_ip_vmi):
    assert_ip_mismatch(vm=report_masquerade_ip_vmi)


@pytest.mark.polarion("CNV-4153")
def test_report_masquerade_ip_after_migration(report_masquerade_ip_vmi):
    src_node = report_masquerade_ip_vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="report-masquerade-ip-migration",
        namespace=report_masquerade_ip_vmi.namespace,
        vmi=report_masquerade_ip_vmi,
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert report_masquerade_ip_vmi.instance.status.nodeName != src_node

    assert_ip_mismatch(vm=report_masquerade_ip_vmi)
