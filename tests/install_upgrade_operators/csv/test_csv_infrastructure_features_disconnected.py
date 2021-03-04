import pytest


@pytest.mark.polarion("CNV-5840")
def test_csv_infrastructure_features_disconnected(csv):
    """
    In the Cluster Service Version check an annotation 'Infrastructure Features' with value 'Disconnected'
    """
    assert (
        '["Disconnected"]'
        in csv.instance.metadata.annotations[
            "operators.openshift.io/infrastructure-features"
        ]
    )
