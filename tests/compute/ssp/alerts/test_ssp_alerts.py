import pytest

from tests.compute.utils import verify_no_listed_alerts_on_cluster


SSP_ALERTS_LIST = [
    "SSPDown",
    "SSPTemplateValidatorDown",
    "SSPCommonTemplatesModificationReverted",
    "SSPHighRateRejectedVms",
    "SSPFailingToReconcile",
]


@pytest.mark.polarion("CNV-7612")
def test_no_ssp_alerts_on_healthy_cluster(
    prometheus,
):
    verify_no_listed_alerts_on_cluster(
        prometheus=prometheus, alerts_list=SSP_ALERTS_LIST
    )
