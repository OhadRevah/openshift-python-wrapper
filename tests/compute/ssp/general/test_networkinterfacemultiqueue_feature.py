"""
Test networkInterfaceMultiqueue feature with cpu core/socket/thread combinations.
"""

import pytest
from pytest_testconfig import config as py_config
from resources.resource import ResourceEditor

from utilities import console
from utilities.virt import wait_for_console, wait_for_vm_interfaces, wait_for_windows_vm


def _update_and_validate_vm_cpu_spec(
    vm, network_multiqueue=True, cores=1, sockets=1, threads=1
):
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
    vm.restart(wait=True)
    cpu_spec = vm.instance.spec.template.spec.domain.cpu
    cpu_topology_xml = vm.vmi.xml_dict["domain"]["cpu"]["topology"]
    assert int(cpu_topology_xml["@cores"]) == cpu_spec.cores == cores
    assert int(cpu_topology_xml["@sockets"]) == cpu_spec.sockets == sockets
    assert int(cpu_topology_xml["@threads"]) == cpu_spec.threads == threads


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        (
            {
                "dv_name": py_config["latest_rhel_version"]["template_labels"]["os"],
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
            {
                "vm_name": py_config["latest_rhel_version"]["template_labels"]["os"],
                "template_labels": {
                    "os": py_config["latest_rhel_version"]["template_labels"]["os"],
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
        wait_for_vm_interfaces(
            vmi=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi
        )
        wait_for_console(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_feature_disabled(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        _update_and_validate_vm_cpu_spec(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            network_multiqueue=False,
        )
        wait_for_vm_interfaces(
            vmi=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi
        )
        wait_for_console(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_cores(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        _update_and_validate_vm_cpu_spec(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class, cores=4
        )
        wait_for_vm_interfaces(
            vmi=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi
        )
        wait_for_console(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_sockets(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        _update_and_validate_vm_cpu_spec(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            sockets=4,
        )
        wait_for_vm_interfaces(
            vmi=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi
        )
        wait_for_console(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_threads(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        _update_and_validate_vm_cpu_spec(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            threads=4,
        )
        wait_for_vm_interfaces(
            vmi=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi
        )
        wait_for_console(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_two_cores_two_sockets_two_threads(
        self, golden_image_vm_instance_from_template_multi_storage_scope_class
    ):
        _update_and_validate_vm_cpu_spec(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            cores=4,
            sockets=2,
            threads=2,
        )
        wait_for_vm_interfaces(
            vmi=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi
        )
        wait_for_console(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            console_impl=console.RHEL,
        )


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        (
            {
                "dv_name": py_config["latest_windows_version"]["template_labels"]["os"],
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
            {
                "vm_name": py_config["latest_windows_version"]["template_labels"]["os"],
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "network_model": "virtio",
                "network_multiqueue": True,
                "wait_for_interfaces_timeout": 1500,
                "ssh": True,
                "username": py_config["windows_username"],
                "password": py_config["windows_password"],
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

    WIN_VER = py_config["latest_windows_version"]["os_version"]

    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3221")
    def test_default_cpu_values(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        wait_for_windows_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            version=self.WIN_VER,
        )

    @pytest.mark.polarion("CNV-3221")
    def test_four_cores_two_sockets_two_threads(
        self,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
    ):
        _update_and_validate_vm_cpu_spec(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            cores=4,
            sockets=2,
            threads=2,
        )
        wait_for_windows_vm(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            version=self.WIN_VER,
        )