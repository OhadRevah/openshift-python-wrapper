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

CNV_TEMPLATES_NAME = [
    "centos6-server-large",
    "centos6-server-medium",
    "centos6-server-small",
    "centos6-server-tiny",
    "centos7-desktop-large",
    "centos7-desktop-medium",
    "centos7-desktop-small",
    "centos7-desktop-tiny",
    "centos7-server-large",
    "centos7-server-medium",
    "centos7-server-small",
    "centos7-server-tiny",
    "centos8-desktop-large",
    "centos8-desktop-medium",
    "centos8-desktop-small",
    "centos8-desktop-tiny",
    "centos8-server-large",
    "centos8-server-medium",
    "centos8-server-small",
    "centos8-server-tiny",
    "fedora-desktop-large",
    "fedora-desktop-medium",
    "fedora-desktop-small",
    "fedora-desktop-tiny",
    "fedora-highperformance-large",
    "fedora-highperformance-medium",
    "fedora-highperformance-small",
    "fedora-highperformance-tiny",
    "fedora-server-large",
    "fedora-server-medium",
    "fedora-server-small",
    "fedora-server-tiny",
    "opensuse-server-large",
    "opensuse-server-medium",
    "opensuse-server-small",
    "opensuse-server-tiny",
    "rhel6-desktop-large",
    "rhel6-desktop-medium",
    "rhel6-desktop-small",
    "rhel6-desktop-tiny",
    "rhel6-server-large",
    "rhel6-server-medium",
    "rhel6-server-small",
    "rhel6-server-tiny",
    "rhel7-desktop-large",
    "rhel7-desktop-medium",
    "rhel7-desktop-small",
    "rhel7-desktop-tiny",
    "rhel7-highperformance-large",
    "rhel7-highperformance-medium",
    "rhel7-highperformance-small",
    "rhel7-highperformance-tiny",
    "rhel7-server-large",
    "rhel7-server-medium",
    "rhel7-server-small",
    "rhel7-server-tiny",
    "rhel8-desktop-large",
    "rhel8-desktop-medium",
    "rhel8-desktop-small",
    "rhel8-desktop-tiny",
    "rhel8-highperformance-large",
    "rhel8-highperformance-medium",
    "rhel8-highperformance-small",
    "rhel8-highperformance-tiny",
    "rhel8-server-large",
    "rhel8-server-medium",
    "rhel8-server-small",
    "rhel8-server-tiny",
    "ubuntu-desktop-large",
    "ubuntu-desktop-medium",
    "ubuntu-desktop-small",
    "ubuntu-desktop-tiny",
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
def base_templates(default_client):
    """ Return templates list by label """
    yield list(
        Template.get(
            default_client,
            singular_name=Template.singular_name,
            label_selector="template.kubevirt.io/type=base",
        )
    )


@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(skip_not_openshift, base_templates):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    base_templates = [template.name for template in base_templates]
    assert len(base_templates) == len(CNV_TEMPLATES_NAME), (
        f"Not all base CNV templates exists\n exist templates:\n "
        f"{base_templates} expected:\n {CNV_TEMPLATES_NAME}",
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
