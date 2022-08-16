import json
import logging

import pytest
from ocp_resources.template import Template
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import py_config

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_OS
from utilities.constants import OPENSHIFT_NAMESPACE, Images
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm


LOGGER = logging.getLogger(__name__)


class CustomTemplate(Template):
    def __init__(
        self,
        name,
        namespace,
        source_template,
        vm_validation_rule=None,
    ):
        """
        Custom template based on a common template.

        Args:
            source_template (Template): Template to be based on
            vm_validation_rule (str, optional): VM validation rule added to the VM annotation

        """
        super().__init__(
            name=name,
            namespace=namespace,
        )
        self.source_template = source_template
        self.vm_validation_rule = vm_validation_rule

    def to_dict(self):
        template_dict = self.source_template.instance.to_dict()
        self.remove_template_metadata_unique_keys(
            template_metadata=template_dict["metadata"]
        )
        template_dict["metadata"].update(
            {
                "labels": {f"{self.ApiGroup.APP_KUBERNETES_IO}/name": self.name},
                "name": self.name,
                "namespace": self.namespace,
            }
        )
        if self.vm_validation_rule:
            template_dict = self.get_template_dict_with_added_vm_validation_rule(
                template_dict=template_dict
            )
        return template_dict

    def get_template_dict_with_added_vm_validation_rule(self, template_dict):
        modified_template_dict = template_dict.copy()
        kubevirt_validation = f"{self.ApiGroup.VM_KUBEVIRT_IO}/validations"
        vm_annotation = modified_template_dict["objects"][0]["metadata"]["annotations"]
        validation_list_string = vm_annotation[kubevirt_validation]
        validation_list = json.loads(validation_list_string)
        validation_list.append(self.vm_validation_rule)
        vm_annotation[kubevirt_validation] = json.dumps(validation_list)
        return modified_template_dict

    @staticmethod
    def remove_template_metadata_unique_keys(template_metadata):
        del template_metadata["resourceVersion"]
        del template_metadata["uid"]
        del template_metadata["creationTimestamp"]


@pytest.fixture()
def custom_template_from_base_template(request, namespace, admin_client):
    base_template = next(
        Template.get(
            admin_client,
            namespace=OPENSHIFT_NAMESPACE,
            name=request.param["base_template_name"],
        )
    )

    with CustomTemplate(
        name=request.param["new_template_name"],
        namespace=namespace.name,
        source_template=base_template,
        vm_validation_rule=request.param.get("validation_rule"),
    ) as custom_template:
        yield custom_template


@pytest.mark.parametrize(
    "custom_template_from_base_template, golden_image_data_volume_scope_function, vm_name",
    [
        pytest.param(
            {
                "base_template_name": f"fedora-{Template.Workload.DESKTOP}-{Template.Flavor.TINY}",
                "new_template_name": "fedora-custom-template-for-test",
            },
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST["image_path"],
                "dv_size": FEDORA_LATEST["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            "vm-from-custom-template",
            marks=pytest.mark.polarion("CNV-7957"),
        ),
        pytest.param(
            {
                "base_template_name": f"rhel9-{Template.Workload.DESKTOP}-{Template.Flavor.TINY}",
                "new_template_name": "custom-rhel9-template-disks-wildcard",
                "validation_rule": {
                    "name": "volumes-validation",
                    "path": "jsonpath::.spec.volumes[*].name",
                    "rule": "string",
                    "message": "the volumes name must be non-empty",
                    "values": ["rootdisk", "cloudinitdisk"],
                },
            },
            {
                "dv_name": "cirros-dv",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
            "vm-from-custom-template-volumes-validation",
            marks=pytest.mark.polarion("CNV-5588"),
        ),
    ],
    indirect=[
        "golden_image_data_volume_scope_function",
        "custom_template_from_base_template",
    ],
)
def test_vm_from_base_custom_template(
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
    custom_template_from_base_template,
    vm_name,
):
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        template_object=custom_template_from_base_template,
        data_source=golden_image_data_source_scope_function,
    ) as custom_vm:
        running_vm(vm=custom_vm)


@pytest.mark.parametrize(
    "custom_template_from_base_template, golden_image_data_volume_scope_function",
    [
        pytest.param(
            {
                "base_template_name": f"rhel9-{Template.Workload.DESKTOP}-{Template.Flavor.TINY}",
                "new_template_name": "custom-rhel9-template-core-validation",
                "validation_rule": {
                    "name": "minimal-required-cpu-core",
                    "path": "jsonpath::.spec.domain.cpu.cores.",
                    "rule": "integer",
                    "message": "This VM has too many cores",
                    "max": 2,
                },
            },
            {
                "dv_name": "cirros-dv",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
        )
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-7958")
def test_custom_template_vm_validation(
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
    custom_template_from_base_template,
):
    with pytest.raises(
        UnprocessibleEntityError, match=r".*This VM has too many cores.*"
    ):
        with VirtualMachineForTestsFromTemplate(
            name="vm-from-custom-template-core-validation",
            namespace=custom_template_from_base_template.namespace,
            client=unprivileged_client,
            template_object=custom_template_from_base_template,
            data_source=golden_image_data_source_scope_function,
            cpu_cores=3,
        ) as vm_from_template:
            pytest.fail(f"VM validation failed on {vm_from_template.name}")
