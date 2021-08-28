import logging

import pytest

from tests.install_upgrade_operators.relationship_labels.constants import (
    ALL_EXPECTED_LABELS_DICTS,
    VERSION_LABEL_KEY,
)
from tests.install_upgrade_operators.relationship_labels.utils import (
    verify_labels_in_hco_components,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def init_labels_dicts(cnv_current_version):
    """
    Populate each labels dict with updates with cnv current version
    """
    for label_dict in ALL_EXPECTED_LABELS_DICTS.copy():
        label_dict[VERSION_LABEL_KEY] = f"v{cnv_current_version}"


class TestRelationshipLabels:
    @pytest.mark.polarion("CNV-7189")
    def test_verify_relationship_labels_hco_components(
        self,
        admin_client,
        hco_namespace,
        init_labels_dicts,
    ):
        LOGGER.info("Verifying labels in HCO components")
        verify_labels_in_hco_components(
            admin_client=admin_client, hco_namespace=hco_namespace
        )
