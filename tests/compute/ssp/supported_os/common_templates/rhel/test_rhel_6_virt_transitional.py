import logging

import pytest
from pytest_testconfig import py_config

from utilities.virt import get_rhel_os_dict, vm_instance_from_template


LOGGER = logging.getLogger(__name__)

RHEL_6 = get_rhel_os_dict(rhel_version="rhel-6-10")
RHEL_VERSION_TEMPLATE_LABELS = RHEL_6["template_labels"]
VIRTIO_TRANSITIONAL = "virtio-transitional"
VIRTIO = "virtio"


@pytest.fixture(scope="class")
def rhel_6_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_class,
    ) as vm:
        yield vm


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, rhel_6_vm",
    [
        pytest.param(
            {
                "dv_name": RHEL_VERSION_TEMPLATE_LABELS["os"],
                "image": RHEL_6["image_path"],
                "dv_size": RHEL_6["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "rhel-6-vm",
                "template_labels": RHEL_VERSION_TEMPLATE_LABELS,
                "guest_agent": False,
            },
        ),
    ],
    indirect=["golden_image_data_volume_scope_class", "rhel_6_vm"],
)
@pytest.mark.ibm_bare_metal
class TestRhel6VirtioTransitional:
    @pytest.mark.polarion("CNV-5852")
    def test_rhel6_template(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_scope_class,
        rhel_6_vm,
    ):
        """
        Verify disk and interface (nic) are set with virtio driver
        """
        devices = rhel_6_vm.vmi.instance.spec.domain.devices
        disk = devices.disks[0].disk.bus == VIRTIO
        nic = devices.interfaces[0].model == VIRTIO
        devices_check = []
        for device in [(disk, "disk"), (nic, "nic")]:
            if not device[0]:
                devices_check.append(f"Device f{devices[1]}, is not set with {VIRTIO}")
        assert (
            not devices_check
        ), f"Some devices are not set with VIRTIO see logs, check list{devices_check}"

    @pytest.mark.polarion("CNV-5874")
    def test_domxml_check(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_scope_class,
        rhel_6_vm,
    ):
        """
        Verify devices: disk,interface,memballoon model is set with: virtio-transitional in VM domxml
        """
        devices = rhel_6_vm.vmi.xml_dict["domain"]["devices"]
        disk = [
            disk["@model"] == VIRTIO_TRANSITIONAL
            for disk in devices["disk"]
            if disk["alias"]["@name"] == f"ua-{rhel_6_vm.name}"
        ]
        interface = devices["interface"]["model"]["@type"] == VIRTIO_TRANSITIONAL
        memballoon = devices["memballoon"]["@model"] == VIRTIO_TRANSITIONAL
        virtio_transitional_check = []
        for model in [
            (disk[0], "disk"),
            (interface, "interface"),
            (memballoon, "memballoon"),
        ]:
            if not model[0]:
                virtio_transitional_check.append(
                    f"Device {model[1]}, is not set with {VIRTIO_TRANSITIONAL}"
                )
        assert (
            not virtio_transitional_check
        ), f"check status:{virtio_transitional_check}"