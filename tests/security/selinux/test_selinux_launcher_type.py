# -*- coding: utf-8 -*-

"""
Test to check, SELinuxLauncher Type in kubevirt config map
"""


import pytest


pytestmark = pytest.mark.post_upgrade


@pytest.mark.polarion("CNV-4296")
def test_selinuxlaunchertype_in_kubevirt_config(kubevirt_config):
    """
    Validate that SELinuxLauncherType in kubevirt config map is virt_launcher.process
    """
    assert kubevirt_config["selinuxLauncherType"] == "virt_launcher.process"
