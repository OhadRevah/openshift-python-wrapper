import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachine
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config

from tests.conftest import vm_instance_from_template
from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    running_vm,
    wait_for_vm_interfaces,
)


pytestmark = pytest.mark.after_upgrade


@pytest.fixture()
def updated_default_storage_class(
    admin_client,
    storage_class_matrix__function__,
    removed_default_storage_classes,
):
    sc_name = [*storage_class_matrix__function__][0]
    if (
        get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=1918294
        )
        not in BUG_STATUS_CLOSED
    ) and sc_name == StorageClass.Types.CEPH_RBD:
        pytest.skip(
            "when default SC is OSC, VM creation will fail as volumeMode is missing."
        )

    sc = list(StorageClass.get(dyn_client=admin_client, name=sc_name))
    with ResourceEditor(
        patches={
            sc[0]: {
                "metadata": {
                    "annotations": {StorageClass.Annotations.IS_DEFAULT_CLASS: "true"},
                    "name": sc_name,
                }
            }
        }
    ):
        yield sc


class DataVolumeTemplatesVirtualMachine(VirtualMachineForTestsFromTemplate):
    def __init__(
        self,
        name,
        namespace,
        client,
        labels,
        data_volume,
        delete_data_volume_sc_params=None,
        updated_storage_class_params=None,
        updated_dv_name=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            labels=labels,
            data_volume=data_volume,
        )
        self.data_volume = data_volume
        self.delete_data_volume_sc_params = delete_data_volume_sc_params
        self.updated_storage_class_params = updated_storage_class_params
        self.updated_dv_name = updated_dv_name

    def to_dict(self):
        res = super().to_dict()
        vm_datavolumetemplates_pvc_spec = res["spec"]["dataVolumeTemplates"][0]["spec"][
            "pvc"
        ]
        if self.delete_data_volume_sc_params:
            vm_datavolumetemplates_pvc_spec.pop("storageClassName")
            vm_datavolumetemplates_pvc_spec.pop("volumeMode")
            # accessModes is mandatory, set to the match the default storage class access mode
            vm_datavolumetemplates_pvc_spec["accessModes"] = [
                self.data_volume.access_modes
            ]
        if self.updated_storage_class_params:
            # Update SC params
            vm_datavolumetemplates_pvc_spec[
                "storageClassName"
            ] = self.updated_storage_class_params["storage_class"]
            vm_datavolumetemplates_pvc_spec[
                "volumeMode"
            ] = self.updated_storage_class_params["access_mode"]
            vm_datavolumetemplates_pvc_spec[
                "volumeMode"
            ] = self.updated_storage_class_params["volume_mode"]
        if self.updated_dv_name:
            res["spec"]["dataVolumeTemplates"][0]["spec"]["source"]["pvc"][
                "name"
            ] = self.updated_dv_name

        return res


@pytest.fixture()
def vm_from_golden_image_multi_storage(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_multi_storage_scope_function,
):
    with DataVolumeTemplatesVirtualMachine(
        name="vm-from-golden-image",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_fedora_version"]["template_labels"]
        ),
        data_volume=golden_image_data_volume_multi_storage_scope_function,
        delete_data_volume_sc_params=request.param.get("delete_sc_params"),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_with_existing_dv(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_function,
    ) as vm:
        yield vm


@pytest.fixture()
def vm_from_golden_image(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_function,
):
    with DataVolumeTemplatesVirtualMachine(
        name="vm-from-golden-image-mismatching-sc",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_fedora_version"]["template_labels"]
        ),
        data_volume=golden_image_data_volume_scope_function,
        updated_storage_class_params=request.param.get("updated_storage_class_params"),
        updated_dv_name=request.param.get("updated_dv_name"),
    ) as vm:
        if request.param.get("start_vm", True):
            running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_missing_golden_image(unprivileged_client, namespace):
    with VirtualMachineForTestsFromTemplate(
        name="vm-missing-golden-image",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_fedora_version"]["template_labels"]
        ),
    ) as vm:
        yield vm


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function, vm_from_golden_image_multi_storage",
    [
        pytest.param(
            {
                "dv_name": py_config["latest_fedora_version"]["template_labels"]["os"],
                "image": py_config["latest_fedora_version"]["image_path"],
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
            },
            {
                "delete_sc_params": True,
            },
            marks=pytest.mark.polarion("CNV-5582"),
        ),
    ],
    indirect=True,
)
def test_vm_from_golden_image_cluster_default_storage_class(
    updated_default_storage_class,
    golden_image_data_volume_multi_storage_scope_function,
    vm_from_golden_image_multi_storage,
):
    vm_from_golden_image_multi_storage.ssh_exec.executor().is_connective()


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_with_existing_dv",
    [
        pytest.param(
            {
                "dv_name": "dv-fedora",
                "image": py_config["latest_fedora_version"]["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
            },
            {
                "vm_name": "fedora-vm",
                "template_labels": py_config["latest_fedora_version"][
                    "template_labels"
                ],
            },
            marks=pytest.mark.polarion("CNV-5530"),
        ),
    ],
    indirect=True,
)
def test_vm_with_existing_dv(data_volume_scope_function, vm_with_existing_dv):
    vm_with_existing_dv.ssh_exec.executor().is_connective()


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_from_golden_image",
    [
        pytest.param(
            {
                "dv_name": py_config["latest_fedora_version"]["template_labels"]["os"],
                "image": py_config["latest_fedora_version"]["image_path"],
                "storage_class": StorageClass.Types.HOSTPATH,
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
            },
            {
                "updated_storage_class_params": {
                    "storage_class": StorageClass.Types.NFS,
                    "access_mode": DataVolume.AccessMode.RWX,
                    "volume_mode": DataVolume.VolumeMode.FILE,
                },
            },
            marks=pytest.mark.polarion("CNV-5529"),
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-5529")
def test_vm_dv_with_different_sc(
    golden_image_data_volume_scope_function, vm_from_golden_image
):
    # VM cloned PVC storage class is different from the original golden image storage class
    # Using NFS and HPP, as Block <> Filesystem is not supported.
    # TODO: Add OCS - HPP test
    vm_from_golden_image.ssh_exec.executor().is_connective()


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_from_golden_image",
    [
        pytest.param(
            {
                "dv_name": "fedora-dv",
                "image": py_config["latest_fedora_version"]["image_path"],
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "updated_dv_name": "non-existing-dv",
                "start_vm": False,
            },
            marks=pytest.mark.polarion("CNV-5528"),
        ),
    ],
    indirect=True,
)
def test_missing_golden_image(
    admin_client,
    namespace,
    golden_image_data_volume_scope_function,
    vm_from_golden_image,
):
    vm_from_golden_image.start()

    # Verify VM error on missing source PVC
    for sample in TimeoutSampler(
        wait_timeout=120,
        sleep=5,
        func=lambda: list(
            VirtualMachine.get(
                dyn_client=admin_client,
                namespace=namespace.name,
                name=vm_from_golden_image.name,
            )
        ),
        exceptions=NotFoundError,
    ):
        if sample and sample[0].instance.status.conditions:
            if (
                f"Source PVC {py_config['golden_images_namespace']}/non-existing-dv doesn't exist"
                in sample[0].instance.status.conditions[0]["message"]
            ):
                break

    # Update VM spec with the correct name
    vm_data_volume_templates_dict = vm_from_golden_image.instance.to_dict()["spec"][
        "dataVolumeTemplates"
    ][0]
    vm_data_volume_templates_dict["spec"]["source"]["pvc"]["name"] = "fedora-dv"
    ResourceEditor(
        patches={
            vm_from_golden_image: {
                "spec": {"dataVolumeTemplates": [vm_data_volume_templates_dict]}
            }
        }
    ).update()

    vm_from_golden_image.wait_for_status(status=True, timeout=480)
    wait_for_vm_interfaces(vmi=vm_from_golden_image.vmi)
