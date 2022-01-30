# -*- coding: utf-8 -*-

"""
Base templates test
"""

import logging
import os
import re

import pytest
from ocp_resources.resource import Resource
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.compute.ssp.constants import HYPERV_FEATURES_LABELS_VM_YAML
from tests.compute.ssp.supported_os.common_templates import utils
from tests.os_params import FEDORA_LATEST_LABELS
from utilities.constants import DATA_SOURCE_NAME, DATA_SOURCE_NAMESPACE, Images
from utilities.infra import BUG_STATUS_CLOSED, JIRA_STATUS_CLOSED, get_jira_status


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

LOGGER = logging.getLogger(__name__)

# SAPHANA has a specific template, needs to be excluded from the collected workloads
LINUX_WORKLOADS_LIST = [
    value
    for key, value in vars(Template.Workload).items()
    if not key.startswith("_") and value != Template.Workload.SAPHANA
]
LINUX_FLAVORS_LIST = [
    value for key, value in vars(Template.Flavor).items() if not key.startswith("_")
]
WINDOWS_FLAVOR_LIST = [Template.Flavor.MEDIUM, Template.Flavor.LARGE]
WINDOWS2K_WORKLOAD_LIST = [Template.Workload.SERVER, Template.Workload.HIGHPERFORMANCE]
WINDOWS10_WORKLOAD_LIST = [Template.Workload.DESKTOP, Template.Workload.HIGHPERFORMANCE]
VM_EXPECTED_ANNOTATION_KEYS = [
    Template.VMAnnotations.FLAVOR,
    Template.VMAnnotations.OS,
    Template.VMAnnotations.WORKLOAD,
]


@pytest.fixture()
def common_templates_expected_list():
    common_templates_list = get_rhel_templates_list()
    common_templates_list += get_fedora_templates_list()
    common_templates_list += get_windows_templates_list()
    common_templates_list += get_centos_templates_list()
    return common_templates_list


def get_rhel_templates_list():
    rhel_major_releases_list = ["6", "7", "8", "9"]
    # RHEL6 - only desktop and server versions are released
    return [
        f"rhel{release}-{workload}-{flavor}"
        for release in rhel_major_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
        if not (release == "6" and workload == Template.Workload.HIGHPERFORMANCE)
    ]


def get_fedora_templates_list():
    return [
        f"fedora-{workload}-{flavor}"
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
    ]


def get_windows_templates_list():
    windows_os_list = [
        "windows10",
        "windows2k12r2",
        "windows2k16",
        "windows2k19",
    ]

    windows_workload_list = []
    for release in windows_os_list:
        if "windows10" in release:
            windows_workload_list.extend(
                [f"{release}-{workload}" for workload in WINDOWS10_WORKLOAD_LIST]
            )
        else:
            windows_workload_list.extend(
                [f"{release}-{workload}" for workload in WINDOWS2K_WORKLOAD_LIST]
            )

    return [
        f"{release}-{flavor}"
        for release in windows_workload_list
        for flavor in WINDOWS_FLAVOR_LIST
    ]


def get_centos_templates_list():
    centos_releases_list = ["7", "-stream8", "-stream9"]
    return [
        f"centos{release}-{workload}-{flavor}"
        for release in centos_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in [Template.Workload.SERVER, Template.Workload.DESKTOP]
    ]


@pytest.fixture()
def windows_base_templates(base_templates):
    windows_templates = [
        template
        for template in base_templates
        if any(
            label.startswith(f"{Template.Labels.OS}/win")
            for label in template.labels.keys()
        )
    ]
    assert windows_templates, "No windows templates found"
    return windows_templates


@pytest.fixture()
def templates_provider_support_dict():
    provider_url_annotation = Template.Annotations.PROVIDER_URL
    support_level_annotation = Template.Annotations.PROVIDER_SUPPORT_LEVEL
    provider_support_dict = {"provider": {Template.Annotations.PROVIDER: "Red Hat"}}
    redhat_support_dict = {
        support_level_annotation: "Full",
        provider_url_annotation: "https://www.redhat.com",
    }
    provider_support_dict.update(
        {
            "windows": redhat_support_dict,
            "rhel": redhat_support_dict,
            "fedora": {
                support_level_annotation: "Community",
                provider_url_annotation: "https://www.fedoraproject.org",
            },
            "centos": {
                support_level_annotation: "Community",
                provider_url_annotation: "https://www.centos.org",
            },
        }
    )

    return provider_support_dict


def update_rhel9_support_dict(template_support_dict):
    if get_jira_status(jira="CNV-11658") not in JIRA_STATUS_CLOSED:
        template_support_dict[Template.Annotations.PROVIDER_SUPPORT_LEVEL] = "Limited"

    return template_support_dict


def verify_annotations_match(obj_annotations, expected):
    return sorted(obj_annotations) == sorted(expected)


@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(
    skip_not_openshift, base_templates, common_templates_expected_list
):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    base_templates = [template.name.split("-v")[0] for template in base_templates]

    assert not set(base_templates) ^ set(common_templates_expected_list), (
        f"Not all base CNV templates exist\n existing templates:\n "
        f"{base_templates} expected:\n {common_templates_expected_list}",
    )


@pytest.mark.parametrize(
    ("os_type", "osinfo_filename", "memory_test"),
    [
        pytest.param(
            "rhel6",
            "rhel-6.10",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3618")),
            id="test_rhel6_minimum_memory",
        ),
        pytest.param(
            "rhel7",
            "rhel-7.7",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3619")),
            id="test_rhel7_minimum_memory",
        ),
        pytest.param(
            "rhel8",
            "rhel-8.1",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3620")),
            id="test_rhel8_minimum_memory",
        ),
        pytest.param(
            "rhel9",
            "rhel-9.0",
            "minimum",
            marks=(pytest.mark.polarion("CNV-6989")),
            id="test_rhel9_minimum_memory",
        ),
        pytest.param(
            "rhel6",
            "rhel-6.10",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3621")),
            id="test_rhel6_maximum_memory",
        ),
        pytest.param(
            "rhel7",
            "rhel-7.7",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3622")),
            id="test_rhel7_maximum_memory",
        ),
        pytest.param(
            "rhel8",
            "rhel-8.1",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3623")),
            id="test_rhel8_maximum_memory",
        ),
        pytest.param(
            "rhel9",
            "rhel-9.0",
            "maximum",
            marks=(pytest.mark.polarion("CNV-6988")),
            id="test_rhel9_maximum_memory",
        ),
    ],
)
def test_validate_rhel_min_max_memory(
    skip_not_openshift,
    base_templates,
    downloaded_latest_libosinfo_db,
    os_type,
    osinfo_filename,
    memory_test,
):
    """
    Validate CNV RHEL templates for minimum and maximum memory, against osinfo db files.
    """

    osinfo_file_path = os.path.join(
        f"{downloaded_latest_libosinfo_db}/os/redhat.com/{osinfo_filename}.xml"
    )
    # libosinfo "all" architecture does not include maximum values
    resources_arch = "all" if memory_test == "minimum" else "x86_64"

    osinfo_memory_value = utils.fetch_osinfo_memory(
        osinfo_file_path=osinfo_file_path,
        memory_test=memory_test,
        resources_arch=resources_arch,
    )

    utils.check_default_and_validation_memory(
        get_base_templates=base_templates,
        osinfo_memory_value=osinfo_memory_value,
        os_type=os_type,
        memory_test=memory_test,
        osinfo_filename=osinfo_filename,
    )


@pytest.mark.parametrize(
    ("osinfo_filename", "os_template", "memory_test"),
    [
        pytest.param(
            "win-2k12r2",
            "windows2k12r2",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3624")),
            id="test_win2kr2_minimum_memory",
        ),
        pytest.param(
            "win-2k16",
            "windows2k16",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3625")),
            id="test_win2k16_minimum_memory",
        ),
        pytest.param(
            "win-2k19",
            "windows2k19",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3626")),
            id="test_win2k19_minimum_memory",
        ),
        pytest.param(
            "win-10",
            "windows10",
            "minimum",
            marks=pytest.mark.polarion("CNV-3627"),
            id="test_win10_minimum_memory",
        ),
        pytest.param(
            "win-2k12r2",
            "windows2k12r2",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3628")),
            id="test_win2k12r2_maximum_memory",
        ),
        pytest.param(
            "win-2k16",
            "windows2k16",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3629")),
            id="test_win2k16_maximum_memory",
        ),
        pytest.param(
            "win-2k19",
            "windows2k19",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3630")),
            id="test_win2k19_maximum_memory",
        ),
        pytest.param(
            "win-10",
            "windows10",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3631")),
            id="test_win10_maximum_memory",
        ),
    ],
)
def test_validate_windows_min_max_memory(
    skip_not_openshift,
    base_templates,
    downloaded_latest_libosinfo_db,
    osinfo_filename,
    os_template,
    memory_test,
):
    """
    Validate CNV Windows templates for minimum and maximum memory, against osinfo db files.
    """

    osinfo_file_path = os.path.join(
        f"{downloaded_latest_libosinfo_db}/os/microsoft.com/{osinfo_filename}.xml"
    )
    osinfo_memory_value = utils.fetch_osinfo_memory(
        osinfo_file_path=osinfo_file_path,
        memory_test=memory_test,
        resources_arch="x86_64",
    )

    utils.check_default_and_validation_memory(
        get_base_templates=base_templates,
        osinfo_memory_value=osinfo_memory_value,
        os_type=os_template,
        memory_test=memory_test,
        osinfo_filename=osinfo_filename,
    )


@pytest.mark.polarion("CNV-4420")
def test_common_templates_machine_type(
    machine_type_from_kubevirt_config, base_templates
):
    """Verify that machine type in templates match the value in kubevirt-config cm"""
    unmatched_templates = [
        template.name
        for template in base_templates
        if template.instance.objects[0].spec.template.spec.domain.machine.type
        != machine_type_from_kubevirt_config
    ]

    assert (
        not unmatched_templates
    ), f"Templates with machine-type that do not match kubevirt cm: {unmatched_templates}"


@pytest.mark.bugzilla(
    2048227, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-5002")
def test_common_templates_golden_images_params(base_templates):
    unmatched_templates = {}
    for template in base_templates:
        template_parameters_dict = template.instance.to_dict()["parameters"]
        # Extract golden images parameters from template's parameters
        golden_images_params = [
            gi_params
            for gi_params in template_parameters_dict
            if gi_params["name"] in [DATA_SOURCE_NAME, DATA_SOURCE_NAMESPACE]
        ]
        if not len(golden_images_params) == 2:
            unmatched_templates.update(
                {template.name: "Missing golden images parameters"}
            )
        for gi_params in golden_images_params:
            # DATA_SOURCE_NAME contains either:
            # fedora OS ("fedora")
            # rhel latest major release (e.g rhel7)
            # Windows relevant OS (e.g win2k19)
            if (
                gi_params["name"] == DATA_SOURCE_NAME
                and re.match(r"^([a-z]+).*", template.name).group(1)[:3]
                not in gi_params["value"]
            ):
                unmatched_templates.update(
                    {
                        template.name: f"{DATA_SOURCE_NAME} wrong value {gi_params['value']}"
                    }
                )
            if (
                gi_params["name"] == DATA_SOURCE_NAMESPACE
                and gi_params["value"] != py_config["golden_images_namespace"]
            ):
                unmatched_templates.update(
                    {
                        template.name: f"{DATA_SOURCE_NAMESPACE} wrong namespace {gi_params['value']}"
                    }
                )
    assert (
        not unmatched_templates
    ), f"The following templates fail on golden images verification: {unmatched_templates}"


@pytest.mark.polarion("CNV-5599")
def test_provide_support_annotations(base_templates, templates_provider_support_dict):
    """Verify provider, provider-support-level and provider-url annotations"""

    def _get_os_support_dict(os_name):
        # Return support dict based on OS
        return {
            **templates_provider_support_dict["provider"],
            **templates_provider_support_dict[os_name],
        }

    unmatched_templates = {}
    for template in base_templates:
        template_annotations_dict = template.instance.to_dict()["metadata"][
            "annotations"
        ]
        template_os_name = re.search(r"([a-z]+).*", template.name).group(1)
        template_support_dict = _get_os_support_dict(os_name=template_os_name)
        # In CNV 4.9, RHEL9 is released as alpha without full support
        if "rhel9" in template.name:
            update_rhel9_support_dict(template_support_dict=template_support_dict)
        for key, value in template_support_dict.items():
            if template_annotations_dict.get(key) != value:
                unmatched_templates[template.name] = template_annotations_dict
                break
    assert (
        not unmatched_templates
    ), f"The following templates fail on provider and support verification: {unmatched_templates}"


@pytest.mark.polarion("CNV-6874")
def test_vm_annotations_in_template(base_templates):
    """Verify template VM object has os, workload and flavor annotations which match corresponding template labels"""

    def _verify_labels_annotations_match(vm_annotations, template_labels):
        """Verify VM annotations match template corresponding labels.
        For example: annotation = vm.kubevirt.io/flavor: medium, label = flavor.template.kubevirt.io/medium: "true"

        Returns:
            True if all annotations are matched else False
        """
        for annotation_name, annotation_value in vm_annotations.items():
            # Construct template label name from the annotation
            # Windows OS in annotation = "windows2k19", in label = "win2k19"
            annotation_value = re.sub("windows", "win", annotation_value)
            label_name = f"{annotation_name.split('/')[-1]}.{Resource.ApiGroup.TEMPLATE_KUBEVIRT_IO}/{annotation_value}"

            # Linux-based OS annotation includes only a major release ("vm.kubevirt.io/os: rhel8")
            # whereas the label includes a minor release ("os.template.kubevirt.io/rhel8.4")
            if not (
                (
                    annotation_name == Template.VMAnnotations.OS
                    and [
                        True for label in template_labels.keys() if label_name in label
                    ]
                )
                or template_labels.get(label_name)
            ):
                return False
        return True

    unmatched_templates = {}
    for template in base_templates:
        vm_object_annotations = template.instance.objects[
            0
        ].spec.template.metadata.annotations
        template_labels = template.instance.metadata.labels

        if not (
            verify_annotations_match(
                obj_annotations=vm_object_annotations.keys(),
                expected=VM_EXPECTED_ANNOTATION_KEYS,
            )
            and _verify_labels_annotations_match(
                vm_annotations=vm_object_annotations, template_labels=template_labels
            )
        ):
            unmatched_templates[template.name] = {
                "annotations": vm_object_annotations,
                "labels": template_labels,
            }

    assert (
        not unmatched_templates
    ), f"Some templates do not have the right VM annotations:\n{unmatched_templates}."


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_from_template_with_existing_dv",
    [
        pytest.param(
            {
                "dv_name": "dv-fedora",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "fedora-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "ssh": False,
                "guest_agent": False,
            },
            marks=pytest.mark.polarion("CNV-6890"),
        ),
    ],
    indirect=True,
)
def test_vmi_annotations(data_volume_scope_function, vm_from_template_with_existing_dv):
    """Verify that VM annotations are copied to the VMI object.
    For this test the underlying OS is not important; using Cirros to reduce runtime.
    """
    vm_annotations = (
        vm_from_template_with_existing_dv.instance.spec.template.metadata.annotations
    )
    # Use only relevant os/flavor/workload annotations
    vmi_annotations = {
        annotation: value
        for annotation, value in vm_from_template_with_existing_dv.vmi.instance.metadata.annotations.items()
        if annotation.startswith(Resource.ApiGroup.VM_KUBEVIRT_IO)
    }

    assert verify_annotations_match(
        obj_annotations=vmi_annotations.keys(), expected=VM_EXPECTED_ANNOTATION_KEYS
    ), f"Unexpected VMI annotations: {vmi_annotations}, expected: {VM_EXPECTED_ANNOTATION_KEYS}"

    assert all(
        [
            vmi_ann_value == vm_annotations[vmi_ann_name]
            for vmi_ann_name, vmi_ann_value in vmi_annotations.items()
        ]
    ), f"vmi annotations {vmi_annotations} do no match vm annotations {vm_annotations}"


@pytest.mark.polarion("CNV-7249")
def test_hyperv_features_exist_in_windows_templates(windows_base_templates):
    templates_with_wrong_hyperv_labels = {}
    for template in windows_base_templates:
        template_hyperv_features = template.instance.objects[
            0
        ].spec.template.spec.domain.features.get("hyperv")
        if sorted(list(template_hyperv_features.keys())) != sorted(
            HYPERV_FEATURES_LABELS_VM_YAML
        ):
            templates_with_wrong_hyperv_labels[template.name] = list(
                template_hyperv_features.keys()
            )
    assert not templates_with_wrong_hyperv_labels, (
        f"Windows templates are missing hyperV labels, hyperV features templates: {HYPERV_FEATURES_LABELS_VM_YAML}\n, "
        f"current templates hyperV labels :{templates_with_wrong_hyperv_labels}"
    )
