import pytest
from pytest_testconfig import config as py_config
from resources.storage_class import StorageClass

from tests.compute.utils import remove_eth0_default_gw
from tests.conftest import vm_instance_from_template
from utilities import console
from utilities.virt import get_guest_os_info, wait_for_console, wait_for_windows_vm


pytestmark = pytest.mark.usefixtures("skip_test_if_no_ocs_sc")


WINDOWS_LATEST = py_config["latest_windows_version"]
RHEL_LATEST = py_config["latest_rhel_version"]
RHEL_VERSION_IMAGE_PATH = RHEL_LATEST["image_path"]
RHEL_VERSION_IMAGE_SIZE = RHEL_LATEST["dv_size"]
RHEL_VERSION_TEMPLATE_LABELS = RHEL_LATEST["template_labels"]
RHEL_DV_NAME = RHEL_VERSION_TEMPLATE_LABELS["os"]
# Use OCS SC for Block disk IO logic
STORAGE_CLASS = StorageClass.Types.CEPH_RBD


def _vm_test_params(
    template_labels,
    disk_io_option=None,
    cpu_threads=None,
):
    return {
        "vm_name": f"vm-disk-io-options-{disk_io_option if disk_io_option else 'auto-driver'}",
        "cpu_threads": cpu_threads,
        "template_labels": template_labels,
        "disk_io_option": disk_io_option,
    }


def check_disk_io_option_on_domain_xml(vm, expected_disk_io_option):
    guest_os_info = get_guest_os_info(vmi=vm.vmi)
    driver_io = None
    if "Windows" not in guest_os_info["name"]:
        for disk_element in vm.vmi.xml_dict["domain"]["devices"]["disk"]:
            if disk_element["alias"]["@name"] == f"ua-{vm.name}":
                driver_io = disk_element["driver"]["@io"]
    else:
        disk = vm.vmi.xml_dict["domain"]["devices"]["disk"]
        if disk["source"]["@dev"] == f"/dev/{vm.name}":
            driver_io = disk["driver"]["@io"]
    assert (
        driver_io == expected_disk_io_option
    ), f"expected:{expected_disk_io_option},found: {driver_io}"


@pytest.fixture()
def disk_options_vm(
    request,
    unprivileged_client,
    rhel7_workers,
    namespace,
    golden_image_data_volume_scope_function,
    network_configuration,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_function,
        network_configuration=network_configuration,
    ) as vm:
        if rhel7_workers:
            remove_eth0_default_gw(vm=vm, console_impl=console.RHEL)
        yield vm


@pytest.fixture()
def windows_vm(
    request,
    disk_options_vm,
):
    wait_for_windows_vm(
        vm=disk_options_vm, version=request.param["os_version"], timeout=2100
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, disk_options_vm, expected_disk_io_option",
    [
        pytest.param(
            {
                "dv_name": RHEL_DV_NAME,
                "image": RHEL_VERSION_IMAGE_PATH,
                "dv_size": RHEL_VERSION_IMAGE_SIZE,
                "storage_class": STORAGE_CLASS,
            },
            _vm_test_params(
                disk_io_option="threads",
                template_labels=RHEL_VERSION_TEMPLATE_LABELS,
            ),
            "threads",
            marks=(pytest.mark.polarion("CNV-4567"),),
        ),
        pytest.param(
            {
                "dv_name": RHEL_DV_NAME,
                "image": RHEL_VERSION_IMAGE_PATH,
                "dv_size": RHEL_VERSION_IMAGE_SIZE,
                "storage_class": STORAGE_CLASS,
            },
            _vm_test_params(
                template_labels=RHEL_VERSION_TEMPLATE_LABELS,
            ),
            "native",
            marks=pytest.mark.polarion("CNV-4560"),
        ),
    ],
    indirect=["golden_image_data_volume_scope_function", "disk_options_vm"],
)
def test_vm_with_disk_io_option_rhel(
    skip_upstream,
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_function,
    disk_options_vm,
    expected_disk_io_option,
):
    wait_for_console(vm=disk_options_vm, console_impl=console.RHEL)
    check_disk_io_option_on_domain_xml(
        vm=disk_options_vm,
        expected_disk_io_option=expected_disk_io_option,
    )


@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, disk_options_vm, windows_vm, expected_disk_io_option",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_LATEST["template_labels"]["os"],
                "image": WINDOWS_LATEST["image_path"],
                "dv_size": WINDOWS_LATEST["dv_size"],
                "storage_class": STORAGE_CLASS,
            },
            {
                **_vm_test_params(
                    template_labels=WINDOWS_LATEST["template_labels"], cpu_threads=2
                ),
                **{
                    "ssh": True,
                    "username": py_config["windows_username"],
                    "password": py_config["windows_password"],
                },
            },
            {"os_version": WINDOWS_LATEST["os_version"]},
            "native",
            marks=pytest.mark.polarion("CNV-4692"),
        ),
    ],
    indirect=[
        "golden_image_data_volume_scope_function",
        "disk_options_vm",
        "windows_vm",
    ],
)
def test_vm_with_disk_io_option_windows(
    skip_upstream,
    namespace,
    golden_image_data_volume_scope_function,
    disk_options_vm,
    windows_vm,
    expected_disk_io_option,
):
    check_disk_io_option_on_domain_xml(
        vm=disk_options_vm,
        expected_disk_io_option=expected_disk_io_option,
    )
