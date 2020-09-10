# -*- coding: utf-8 -*-

"""
Base templates test
"""

import logging
import os

import pytest
from resources.template import Template
from tests.compute.ssp.supported_os.common_templates import utils


LOGGER = logging.getLogger(__name__)

LINUX_WORKLOADS_LIST = ["tiny", "small", "medium", "large"]
LINUX_FLAVORS_LIST = ["desktop", "highperformance", "server"]


@pytest.fixture()
def common_templates_expected_list():
    common_templates_list = get_rhel_templates_list()
    common_templates_list += get_fedora_templates_list()
    common_templates_list += get_windows_templates_list()
    return common_templates_list


def get_rhel_templates_list():
    rhel_major_releases_list = ["6", "7", "8"]
    # RHEL6 - only desktop and server versions are released
    return [
        f"rhel{release}-{flavor}-{workload}"
        for release in rhel_major_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
        if not (release == "6" and flavor == "highperformance")
    ]


def get_fedora_templates_list():
    return [
        f"fedora-{flavor}-{workload}"
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
    ]


def get_windows_templates_list():
    return [
        "win2k12r2-desktop-large",
        "win2k12r2-desktop-medium",
        "win2k12r2-server-large",
        "win2k12r2-server-medium",
        "windows-server-large",
        "windows-server-medium",
        "windows10-desktop-large",
        "windows10-desktop-medium",
    ]


@pytest.fixture(scope="module")
def base_templates(admin_client):
    """ Return templates list by label """
    yield list(
        Template.get(
            admin_client,
            singular_name=Template.singular_name,
            label_selector="template.kubevirt.io/type=base",
        )
    )


@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(
    skip_not_openshift, base_templates, common_templates_expected_list
):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    base_templates = [template.name.split("-v")[0] for template in base_templates]

    assert not set(base_templates) ^ set(common_templates_expected_list), (
        f"Not all base CNV templates exists\n exist templates:\n "
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
            "windows-server",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3624")),
            id="test_win2kr2_minimum_memory",
        ),
        pytest.param(
            "win-2k16",
            "windows-server",
            "minimum",
            marks=(pytest.mark.polarion("CNV-3625")),
            id="test_win2k16_minimum_memory",
        ),
        pytest.param(
            "win-2k19",
            "windows-server",
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
            "windows-server",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3628")),
            id="test_win2k12r2_maximum_memory",
        ),
        pytest.param(
            "win-2k16",
            "windows-server",
            "maximum",
            marks=(pytest.mark.polarion("CNV-3629")),
            id="test_win2k16_maximum_memory",
        ),
        pytest.param(
            "win-2k19",
            "windows-server",
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
