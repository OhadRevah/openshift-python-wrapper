"""
Automation for Hot Plug
"""
import pytest
from ocp_resources.resource import ResourceEditor


@pytest.fixture()
def feature_gate_data(kubevirt_config_cm):
    return kubevirt_config_cm.instance["data"]["feature-gates"].split(",")


@pytest.fixture()
def enabled_hotplugvolumes_feature_gate(hyperconverged_resource):
    with ResourceEditor(
        patches={
            hyperconverged_resource: {
                "spec": {"featureGates": {"hotplugVolumes": True}}
            }
        }
    ) as edits:
        yield edits


@pytest.mark.polarion("CNV-5508")
def test_hotplugvolumes_feature_gate(
    enabled_hotplugvolumes_feature_gate, feature_gate_data
):
    assert "HotplugVolumes" in feature_gate_data
