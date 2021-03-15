"""
Test networkInterfaceMultiqueue feature with cpu core/socket/thread combinations.
"""

import pytest
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import config as py_config

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
    vm.ssh_exec.executor().is_connective(tcp_timeout=120)
    validate_vm_cpu_spec(vm=vm, cores=cores, sockets=sockets, threads=threads)


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        (
            {
                "dv_name": py_config["latest_rhel_os_dict"]["template_labels"]["os"],
                "image": py_config["latest_rhel_os_dict"]["image_path"],
                "dv_size": py_config["latest_rhel_os_dict"]["dv_size"],
            },
            {
                "vm_name": py_config["latest_rhel_os_dict"]["template_labels"]["os"],
                "template_labels": {
                    "os": py_config["latest_rhel_os_dict"]["template_labels"]["os"],
                    "workload": "desktop",
                    "flavor": "large",
                },
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("golden_image_data_volume_multi_storage_scope_class")
class TestLatestRHEL:
    """
    Test networkInterfaceMultiqueue on latest RHEL with different cpu core/socket/thread combinations.
    """

    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3221")
    def test_default_cpu_values(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        golden_image_vm_instance_from_template_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
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
                "dv_name": py_config["latest_windows_os_dict"]["template_labels"]["os"],
                "image": py_config["latest_windows_os_dict"]["image_path"],
                "dv_size": py_config["latest_windows_os_dict"]["dv_size"],
            },
            {
                "vm_name": py_config["latest_windows_os_dict"]["template_labels"]["os"],
                "template_labels": py_config["latest_windows_os_dict"][
                    "template_labels"
                ],
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

    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3221")
    def test_default_cpu_values(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        golden_image_vm_instance_from_template_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
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
