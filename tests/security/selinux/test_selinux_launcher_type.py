# -*- coding: utf-8 -*-

"""
Test to check, SELinuxLauncher Type in kubevirt config map
"""


import pytest


pytestmark = pytest.mark.after_upgrade


@pytest.mark.polarion("CNV-4296")
def test_selinuxlaunchertype_in_kubevirt_config(kubevirt_config_cm):
    """
    Validate that SELinuxLauncherType in kubevirt config map is virt_launcher.process
    """
    assert (
        kubevirt_config_cm.instance.data.selinuxLauncherType == "virt_launcher.process"
    )
