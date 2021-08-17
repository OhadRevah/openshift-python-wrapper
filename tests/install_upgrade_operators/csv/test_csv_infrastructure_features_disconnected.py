import ast

import pytest


@pytest.mark.polarion("CNV-5840")
def test_csv_infrastructure_features_disconnected(csv):
    """
    In the Cluster Service Version aannotations for Infrastructure Feature disconnected looks like:
    '["disconnected", "proxy-aware"]'.
    check an annotation 'Infrastructure Features' with value 'disconnected'
    """
    csv_annotations = ast.literal_eval(
        node_or_string=csv.instance.metadata.annotations[
            "operators.openshift.io/infrastructure-features"
        ]
    )
    for infra_feature in csv_annotations:
        if infra_feature.lower() == "disconnected":
            return True
    else:
        pytest.fail(
            f"Disconnected Infrastructure feature is not found {csv_annotations}"
        )
