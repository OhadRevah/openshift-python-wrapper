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

from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)


LOGGER = logging.getLogger(__name__)

LINUX_WORKLOADS_LIST = [
    value for key, value in vars(Template.Workload).items() if not key.startswith("_")
]
LINUX_FLAVORS_LIST = [
    value for key, value in vars(Template.Flavor).items() if not key.startswith("_")
]
WINDOWS_FLAVOR_LIST = [Template.Flavor.MEDIUM, Template.Flavor.LARGE]


@pytest.fixture()
def common_templates_expected_list():
    common_templates_list = get_rhel_templates_list()
    common_templates_list += get_fedora_templates_list()
    common_templates_list += get_windows_templates_list()
    common_templates_list += get_centos_templates_list()
    return common_templates_list


def get_rhel_templates_list():
    rhel_major_releases_list = ["6", "7", "8"]
    # RHEL6 - only desktop and server versions are released
    return [
        f"rhel{release}-{workload}-{flavor}"
        for release in rhel_major_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
        if not (release == "6" and workload == Template.Workload.HIGH_PERFORMANCE)
    ]


def get_fedora_templates_list():
    return [
        f"fedora-{workload}-{flavor}"
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
    ]


def get_windows_templates_list():
    windows_releases_list = [
        "windows10-desktop",
        "windows2k12r2-server",
        "windows2k16-server",
        "windows2k19-server",
    ]
    return [
        f"{release}-{flavor}"
        for release in windows_releases_list
        for flavor in WINDOWS_FLAVOR_LIST
    ]


def get_centos_templates_list():
    centos_releases_list = ["7", "8"]
    return [
        f"centos{release}-{workload}-{flavor}"
        for release in centos_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in [Template.Workload.SERVER, Template.Workload.DESKTOP]
    ]


@pytest.fixture(scope="module")
def base_templates(admin_client):
    """ Return templates list by label """
    common_templates_list = list(
        Template.get(
            dyn_client=admin_client,
            singular_name=Template.singular_name,
            label_selector=Template.Labels.BASE,
        )
    )
    # TODO: remove once bug 1925019 is fixed ("deprecated" label should be added to older templates)
    # After upgrade, os.template.kubevirt.io/<os name> label is removed from older templates
    # but not all deprecated templates have "deprecated" annotation.
    if (
        get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=1925019
        )
        not in BUG_STATUS_CLOSED
    ):
        return [
            template
            for template in common_templates_list
            if [
                label
                for label in template.labels
                if label[0].startswith(f"{Resource.ApiGroup.OS_TEMPLATE_KUBEVIRT_IO}/")
            ]
        ]

    return [
        template
        for template in common_templates_list
        if not template.instance.metadata.annotations.get(
            Template.Annotations.DEPRECATED
        )
    ]


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
    ],
)
def test_validate_rhel_min_max_memory(
    skip_not_openshift,
    base_templates,
    fetch_osinfo_path,
    os_type,
    osinfo_filename,
    memory_test,
):
    """
    Validate CNV RHEL templates for minimum and maximum memory, against osinfo db files.
    """

    osinfo_file_path = os.path.join(
        f"{fetch_osinfo_path}/os/redhat.com/{osinfo_filename}.xml"
    )
    osinfo_memory_value = utils.fetch_osinfo_memory(
        osinfo_file_path=osinfo_file_path, memory_test=memory_test, resources_arch="all"
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
    fetch_osinfo_path,
    osinfo_filename,
    os_template,
    memory_test,
):
    """
    Validate CNV Windows templates for minimum and maximum memory, against osinfo db files.
    """

    osinfo_file_path = os.path.join(
        f"{fetch_osinfo_path}/os/microsoft.com/{osinfo_filename}.xml"
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
    machine_type_from_kubevirt_config_cm, base_templates
):
    """ Verify that machine type in templates match the value in kubevirt-config cm """
    unmatched_templates = [
        template.name
        for template in base_templates
        if template.instance.objects[0].spec.template.spec.domain.machine.type
        != machine_type_from_kubevirt_config_cm
    ]

    assert (
        not unmatched_templates
    ), f"Templates with machine-type that do not match kubevirt cm: {unmatched_templates}"


@pytest.mark.polarion("CNV-5002")
def test_common_templates_golden_images_params(base_templates):
    unmatched_templates = {}
    for template in base_templates:
        template_parameters_dict = template.instance.to_dict()["parameters"]
        # Extract golden images parameters from template's parameters
        golden_images_params = [
            gi_params
            for gi_params in template_parameters_dict
            if gi_params["name"] in ["SRC_PVC_NAME", "SRC_PVC_NAMESPACE"]
        ]
        if not len(golden_images_params) == 2:
            unmatched_templates.update(
                {template.name: "Missing golden images parameters"}
            )
        for gi_params in golden_images_params:
            # SRC_PVC_NAME conatins either:
            # fedora latest OS (e.g fedora32)
            # rhel latest major release (e.g rhel7)
            # Windows relevant OS (e.g win2k19)
            if (
                gi_params["name"] == "SRC_PVC_NAME"
                and re.match(r"^([a-z]+).*", template.name).group(1)[:3]
                not in gi_params["value"]
            ):
                unmatched_templates.update(
                    {template.name: f"SRC_PVC_NAME wrong value {gi_params['value']}"}
                )
            if (
                gi_params["name"] == "SRC_PVC_NAMESPACE"
                and gi_params["value"] != py_config["golden_images_namespace"]
            ):
                unmatched_templates.update(
                    {
                        template.name: f"SRC_PVC_NAMESPACE wrong namespace {gi_params['value']}"
                    }
                )
    assert (
        not unmatched_templates
    ), f"The following templates fail on golden images verification: {unmatched_templates}"


@pytest.mark.polarion("CNV-5599")
def test_provide_support_annotations(base_templates, templates_provider_support_dict):
    """ Verify provider, provider-support-level and provider-url annotations"""

    def _get_os_support_dict(os_name):
        # Return support dict based on OS
        return {
            **templates_provider_support_dict["provider"],
            **templates_provider_support_dict[os_name],
        }

    unmatched_templates = {}
    for template in base_templates:
        # RHEL 6 templates to do not have the provider annotations
        if "rhel6" not in template.name:
            template_annotations_dict = template.instance.to_dict()["metadata"][
                "annotations"
            ]
            template_os_name = re.search(r"([a-z]+).*", template.name).group(1)
            for key, value in _get_os_support_dict(os_name=template_os_name).items():
                if template_annotations_dict.get(key) != value:
                    unmatched_templates[template.name] = template_annotations_dict
                    break
    assert (
        not unmatched_templates
    ), f"The following templates fail on provider and support verification: {unmatched_templates}"
