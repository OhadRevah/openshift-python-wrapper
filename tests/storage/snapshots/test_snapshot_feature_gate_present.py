import pytest


@pytest.mark.polarion("CNV-5781")
def test_snapshot_feature_gate_present(kubevirt_feature_gates):
    """
    This test will ensure that 'Snapshot' feature gate is present in KubeVirt ConfigMap.
    """
    assert "Snapshot" in kubevirt_feature_gates
