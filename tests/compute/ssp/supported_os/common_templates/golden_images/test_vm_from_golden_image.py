import logging

import pytest
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.virt import wait_for_console, wait_for_windows_vm


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures("skip_upstream", "namespace")


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class, vm_instance_from_template_golden_image_multi_scope_class",
    [
        pytest.param(
            {
                "dv_name": "rhel-dv-source",
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_namespace": py_config["golden_images_namespace"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
            {
                "vm_name": "rhel-vm-from-image",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "target_dv_name": "rhel-dv-target",
                "vm_wait_timeout": 1200,
            },
        ),
    ],
    indirect=True,
)
class TestRhelGoldenImages:
    @pytest.mark.polarion("CNV-4493")
    def test_vm_from_rhel_golden_image(
        self,
        vm_instance_from_template_golden_image_multi_scope_class,
    ):
        wait_for_console(
            vm=vm_instance_from_template_golden_image_multi_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.polarion("CNV-4855")
    def test_rhel_golden_image_vm_migration(
        self,
        skip_access_mode_rwo_scope_class,
        vm_instance_from_template_golden_image_multi_scope_class,
    ):
        utils.migrate_vm(vm=vm_instance_from_template_golden_image_multi_scope_class)

        wait_for_console(
            vm=vm_instance_from_template_golden_image_multi_scope_class,
            console_impl=console.RHEL,
        )


@pytest.mark.tier3
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_golden_image_multi_scope_function",
    [
        pytest.param(
            {
                "dv_name": "windows-dv-source",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_namespace": py_config["golden_images_namespace"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
            {
                "vm_name": "windows-vm-from-image",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "target_dv_name": "windows-dv-target",
                "vm_wait_timeout": 3600,
                "wait_for_interfaces_timeout": 1800,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-4495")
def test_vm_from_windows_golden_image(
    vm_instance_from_template_golden_image_multi_scope_function,
    winrmcli_pod_scope_function,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_golden_image_multi_scope_function,
        version=py_config["latest_windows_version"]["os_version"],
        winrmcli_pod=winrmcli_pod_scope_function,
        timeout=1800,
    )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_golden_image_multi_scope_function",
    [
        pytest.param(
            {
                "dv_name": "fedora-dv-source",
                "image": py_config["latest_fedora_version"]["image_path"],
                "dv_namespace": py_config["golden_images_namespace"],
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
            },
            {
                "vm_name": "fedora-vm-from-image",
                "template_labels": py_config["latest_fedora_version"][
                    "template_labels"
                ],
                "target_dv_name": "fedora-dv-target",
                "vm_wait_timeout": 1200,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-4583")
def test_vm_from_fedora_golden_image(
    vm_instance_from_template_golden_image_multi_scope_function,
):
    wait_for_console(
        vm=vm_instance_from_template_golden_image_multi_scope_function,
        console_impl=console.Fedora,
    )
