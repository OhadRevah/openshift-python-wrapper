"""
Automation for Hot Plug
"""
import pytest


pytestmark = pytest.mark.post_upgrade


@pytest.mark.polarion("CNV-5508")
def test_hotplugvolumes_feature_gate(kubevirt_feature_gates):
    assert "HotplugVolumes" in kubevirt_feature_gates
