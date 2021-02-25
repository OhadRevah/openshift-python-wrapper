import pytest


@pytest.mark.polarion("CNV-5781")
def test_snapshot_feature_gate_present(feature_gate_data):
    """
    This test will ensure that 'Snapshot' feature gate is present in KubeVirt ConfigMap.
    """
    assert "Snapshot" in feature_gate_data
