"""
Test networkInterfaceMultiqueue feature with cpu core/socket/thread combinations.
"""

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_OS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
    WINDOWS_LATEST_OS,
)
from utilities.constants import TIMEOUT_2MIN
from utilities.virt import wait_for_vm_interfaces


pytestmark = pytest.mark.post_upgrade


def update_cpu_spec(vm, network_multiqueue=True, cores=1, sockets=1, threads=1):
    ResourceEditor(
        {
            vm: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "cpu": {
                                    "cores": cores,
                                    "sockets": sockets,
                                    "threads": threads,
                                },
                                "devices": {
                                    "networkInterfaceMultiqueue": network_multiqueue
                                },
                            }
                        }
                    }
                }
            }
        }
    ).update()


def validate_vm_cpu_spec(vm, cores=1, sockets=1, threads=1):
    cpu_spec = vm.instance.spec.template.spec.domain.cpu
    cpu_topology_xml = vm.vmi.xml_dict["domain"]["cpu"]["topology"]
    assert int(cpu_topology_xml["@cores"]) == cpu_spec.cores == cores
    assert int(cpu_topology_xml["@sockets"]) == cpu_spec.sockets == sockets
    assert int(cpu_topology_xml["@threads"]) == cpu_spec.threads == threads


def update_validate_cpu_in_vm(
    vm, network_multiqueue=True, cores=1, sockets=1, threads=1
):
    update_cpu_spec(
        vm=vm,
        network_multiqueue=network_multiqueue,
        cores=cores,
        sockets=sockets,
        threads=threads,
    )
    vm.restart(wait=True)
    wait_for_vm_interfaces(vmi=vm.vmi)
    vm.ssh_exec.executor().is_connective(tcp_timeout=TIMEOUT_2MIN)
    validate_vm_cpu_spec(vm=vm, cores=cores, sockets=sockets, threads=threads)


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        (
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": RHEL_LATEST_OS,
                "template_labels": {
                    "os": RHEL_LATEST_OS,
                    "workload": Template.Workload.SERVER,
                    "flavor": Template.Flavor.LARGE,
                },
            },
        )
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.usefixtures("golden_image_data_volume_multi_storage_scope_class")
class TestLatestRHEL:
    """
    Test networkInterfaceMultiqueue on latest RHEL with different cpu core/socket/thread combinations.
    """

    @pytest.mark.order("first")
    @pytest.mark.polarion("CNV-3221")
    def test_default_cpu_values(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        golden_image_vm_instance_from_template_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=TIMEOUT_2MIN
        )

    @pytest.mark.polarion("CNV-3221")
    def test_feature_disabled(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        update_validate_cpu_in_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            network_multiqueue=False,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_cores(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        update_validate_cpu_in_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class, cores=4
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_sockets(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        update_validate_cpu_in_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            sockets=4,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_threads(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        update_validate_cpu_in_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            threads=4,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_two_cores_two_sockets_two_threads(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        update_validate_cpu_in_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            cores=4,
            sockets=2,
            threads=2,
        )


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        (
            {
                "dv_name": WINDOWS_LATEST_OS,
                "image": WINDOWS_LATEST["image_path"],
                "dv_size": WINDOWS_LATEST["dv_size"],
            },
            {
                "vm_name": WINDOWS_LATEST_OS,
                "template_labels": WINDOWS_LATEST_LABELS,
                "network_model": "virtio",
                "network_multiqueue": True,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("golden_image_data_volume_multi_storage_scope_class")
class TestLatestWindows:
    """
    Test networkInterfaceMultiqueue on latest Windows with different cpu core/socket/thread combinations.
    """

    @pytest.mark.order("first")
    @pytest.mark.polarion("CNV-3221")
    def test_default_cpu_values(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        golden_image_vm_instance_from_template_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=TIMEOUT_2MIN
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_cores_two_sockets_two_threads(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        update_validate_cpu_in_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            cores=4,
            sockets=2,
            threads=2,
        )
