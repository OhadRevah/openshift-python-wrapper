"""
Automation for Hot Plug
"""
import pytest

from utilities.infra import BUG_STATUS_CLOSED


@pytest.fixture()
def feature_gate_data(kubevirt_config_cm):
    return kubevirt_config_cm.instance["data"]["feature-gates"].split(",")


@pytest.mark.bugzilla(
    1910857, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-5508")
def test_hotplugvolumes_feature_gate(feature_gate_data):
    assert "HotplugVolumes" in feature_gate_data
