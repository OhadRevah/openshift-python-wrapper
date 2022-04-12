import logging

import pytest

from tests.install_upgrade_operators.constants import (
    SRIOV_LIVEMIGRATION,
    WORKLOADUPDATEMETHODS,
)
from utilities.constants import LIVE_MIGRATE


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures("skip_if_not_sno_cluster")
class TestDefaultSNO:
    @pytest.mark.parametrize(
        "fg_name",
        [
            pytest.param(
                LIVE_MIGRATE,
                marks=(pytest.mark.polarion("CNV-8384")),
                id="test_sno_kubevirt_no_livemigrate",
            ),
            pytest.param(
                SRIOV_LIVEMIGRATION,
                marks=(pytest.mark.polarion("CNV-8385")),
                id="test_sno_kubevirt_no_sriov_livemigrate",
            ),
        ],
    )
    def test_default_fg(self, kubevirt_feature_gates, fg_name):
        assert (
            fg_name not in kubevirt_feature_gates
        ), f"Featuregate {fg_name} exists in {kubevirt_feature_gates}"

    @pytest.mark.polarion("CNV-8475")
    def test_default_workload_update_strategy(
        self, kubevirt_hyperconverged_spec_scope_module
    ):
        assert WORKLOADUPDATEMETHODS not in kubevirt_hyperconverged_spec_scope_module, (
            f"{WORKLOADUPDATEMETHODS} is not disabled on"
            f"SNO cluster: {kubevirt_hyperconverged_spec_scope_module}"
        )
