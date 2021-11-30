import pytest


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
    fired_alerts = {}
    for alert in SSP_ALERTS_LIST:
        query = f'ALERTS{{alertname="{alert}"}}'
        result = prometheus.query(query=query)["data"]["result"]
        if result:
            fired_alerts[alert] = result

    assert (
        not fired_alerts
    ), f"Alerts should not be fired on healthy cluster.\n {fired_alerts}"
