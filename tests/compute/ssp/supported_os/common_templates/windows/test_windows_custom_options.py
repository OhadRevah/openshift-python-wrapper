import shlex

import pytest
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.template import Template
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from pytest_testconfig import py_config

from tests.compute.ssp.constants import VIRTIO
from utilities.constants import TIMEOUT_12MIN
from utilities.infra import run_ssh_commands
from utilities.network import LINUX_BRIDGE, network_device, network_nad
from utilities.storage import get_storage_class_dict_from_matrix
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_windows_os_dict,
    running_vm,
)


WINDOWS_19 = get_windows_os_dict(windows_version="win-19")

FIRMWARE_UUID = "A6074E4A-13ED-5222-9CC5-4DC445BE1EC5"
TESTS_CLASS_NAME = "TestCustomWindowsOptions"


class CustomWindowsVM(VirtualMachineForTestsFromTemplate):
    def __init__(
        self,
        name,
        namespace,
        client,
        data_source,
        os_dict,
        nad,
        drive_d_pvc,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            data_source=data_source,
            labels=Template.generate_template_labels(**os_dict["template_labels"]),
            cpu_cores=1,
            cpu_sockets=2,
            cpu_model="host-model",
        )

        self.nad = nad
        self.drive_d_pvc = drive_d_pvc

    def to_dict(self):
        res = super().to_dict()
        spec = res["spec"]["template"]["spec"]
        domain = spec["domain"]

        disks = domain["devices"]["disks"]
        disks[0]["disk"]["bus"] = VIRTIO
        disks[0]["bootOrder"] = 2

        disks.append({"disk": {"bus": VIRTIO}, "name": "windows-custom-d"})

        interfaces = domain["devices"]["interfaces"]
        interfaces[0]["model"] = "virtio"
        interfaces.append(
            {
                "name": "vnic0",
                "bridge": {},
                "bootOrder": 1,
            }
        )

        domain["firmware"] = {"uuid": FIRMWARE_UUID}

        domain["resources"]["requests"] = {
            "memory": "11Gi",
            "cpu": "1500m",
        }

        spec["networks"].append(
            {"multus": {"networkName": self.nad.name}, "name": "vnic0"}
        )

        spec["volumes"].append(
            {
                "persistentVolumeClaim": {"claimName": self.drive_d_pvc.name},
                "name": self.drive_d_pvc.name,
            }
        )

        return res


def assert_firmware_uuid_in_domxml(vm, uuid):
    xml_domain = vm.vmi.xml_dict["domain"]
    assert (
        xml_domain.get("uuid", "").lower() == uuid.lower()
    ), f"Firmware UUID not found in domxml for {custom_windows_vm.name}"


def initialize_and_format_windows_drive(
    vm, disk_number, partition_number, drive_letter
):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            shlex.split(cmd)
            for cmd in [
                f'powershell -command "initialize-disk -number {disk_number}"',
                f'powershell -command "new-partition -disknumber {disk_number} -usemaximumsize"',
                f'powershell -command "set-partition -disknumber {disk_number} -partitionnumber {partition_number} '
                f'-newdriveletter {drive_letter}"',
                f'powershell -command "format-volume -driveletter {drive_letter} -filesystem NTFS"',
            ]
        ],
        get_pty=True,
    )


@pytest.fixture(scope="class")
def windows_custom_bridge(
    hosts_common_available_ports,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="br1-win-custom-nnc",
        interface_name="br1-win-custom",
    ) as br:
        yield br


@pytest.fixture(scope="class")
def windows_custom_bridge_nad(windows_custom_bridge, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=windows_custom_bridge.bridge_type,
        nad_name="br1-win-custom-nad",
        interface_name=(windows_custom_bridge.bridge_name),
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def windows_custom_drive_d(unprivileged_client, namespace):
    storage_class = py_config["default_storage_class"]
    storage_class_dict = get_storage_class_dict_from_matrix(
        storage_class=storage_class
    )[storage_class]
    with PersistentVolumeClaim(
        name="windows-custom-d",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class,
        accessmodes=storage_class_dict["access_mode"],
        volume_mode=storage_class_dict["volume_mode"],
        size="15Gi",
    ) as pvc:
        yield pvc


@pytest.fixture(scope="class")
def custom_windows_vm(
    request,
    windows_custom_bridge,
    windows_custom_bridge_nad,
    windows_custom_drive_d,
    golden_image_data_source_scope_class,
    unprivileged_client,
):
    with CustomWindowsVM(
        name="custom-windows-vm",
        namespace=windows_custom_bridge_nad.namespace,
        client=unprivileged_client,
        data_source=golden_image_data_source_scope_class,
        os_dict=request.param,
        nad=windows_custom_bridge_nad,
        drive_d_pvc=windows_custom_drive_d,
    ) as vm:
        yield vm


@pytest.mark.ibm_bare_metal
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, custom_windows_vm",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_19["template_labels"]["os"],
                "image": WINDOWS_19["image_path"],
                "dv_size": "100Gi",
                "storage_class": py_config["default_storage_class"],
            },
            WINDOWS_19,
            id=WINDOWS_19["template_labels"]["os"],
            marks=pytest.mark.polarion("CNV-7496"),
        ),
    ],
    indirect=True,
)
class TestCustomWindowsOptions:
    @pytest.mark.polarion("CNV-7496")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::boot")
    def test_windows_custom_options_boot_and_domxml(self, custom_windows_vm):
        running_vm(vm=custom_windows_vm)

    @pytest.mark.polarion("CNV-7960")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::domxml", depends=[f"{TESTS_CLASS_NAME}::boot"]
    )
    def test_windows_custom_options_fw_uuid_in_domxml(self, custom_windows_vm):
        assert_firmware_uuid_in_domxml(vm=custom_windows_vm, uuid=FIRMWARE_UUID)

    @pytest.mark.polarion("CNV-7956")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::initialize disk",
        depends=[f"{TESTS_CLASS_NAME}::boot"],
    )
    def test_windows_custom_options_initialize_disk(
        self, custom_windows_vm, windows_custom_drive_d
    ):
        initialize_and_format_windows_drive(
            vm=custom_windows_vm, disk_number=1, partition_number=2, drive_letter="D"
        )

    @pytest.mark.polarion("CNV-7886")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migration", depends=[f"{TESTS_CLASS_NAME}::boot"]
    )
    def test_windows_custom_options_migration(self, custom_windows_vm):
        with VirtualMachineInstanceMigration(
            name="custom-windows-vm-migration",
            namespace=custom_windows_vm.namespace,
            vmi=custom_windows_vm.vmi,
        ) as mig:
            mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=TIMEOUT_12MIN)