import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_related_objects,
)


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


class TestRelatedObjects:
    @pytest.mark.polarion("CNV-7267")
    def test_hco_related_objects(
        self,
        ocp_resources_submodule_list,
        hco_status_related_objects,
        hco_namespace,
        admin_client,
    ):
        validate_related_objects(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            ocp_resources_submodule_list=ocp_resources_submodule_list,
            related_objects=hco_status_related_objects,
        )
