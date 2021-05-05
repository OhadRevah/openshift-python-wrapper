import logging
from collections import defaultdict

from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler


LOGGER = logging.getLogger(__name__)
KUBEVIRT_CR_ALERT_NAME = "KubevirtHyperconvergedClusterOperatorCRModification"


def prometheus_query(prometheus, query):
    """
    Perform a Prometheus query and retrieves associated results.

    Args:
        prometheus (Fixture): Prometheus fixture returns it's object.
        query (String): Prometheus query string (for strings with special characters
        they need to be parsed by the caller)

    Returns:
        Dictionary: Query response.
    """
    query_response = prometheus.query(query=query)
    assert (
        query_response["status"] == "success"
    ), f"Prometheus qpi query: {query} failed: {query_response}"
    return query_response


def get_metric_by_prometheus_query(prometheus, query):

    response = prometheus_query(
        prometheus=prometheus, query=f"/api/v1/query?query={query}"
    )
    return response


def get_all_mutation_values_from_prometheus(prometheus):
    query_response = get_metric_by_prometheus_query(
        prometheus=prometheus,
        query="kubevirt_hco_out_of_band_modifications_count",
    )
    metric_results = query_response["data"].get("result", [])
    component_dict = defaultdict(int)
    for result in metric_results:
        component_dict[result["metric"]["component_name"]] += int(result["value"][1])
    return dict(component_dict)


def get_mutation_component_value_from_prometheus(prometheus, component_name):
    component_dict = get_all_mutation_values_from_prometheus(prometheus=prometheus)
    return component_dict.get(component_name, 0)


def get_changed_mutation_component_value(prometheus, component_name, previous_value):
    samples = TimeoutSampler(
        wait_timeout=300,
        sleep=1,
        func=get_mutation_component_value_from_prometheus,
        prometheus=prometheus,
        component_name=component_name,
    )
    try:
        for sample in samples:
            if sample != previous_value:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(
            f"component value did not change for component_name '{component_name}'."
        )
        raise


def get_all_prometheus_alerts(prometheus):
    """This function will give all alerts.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.

    Returns:
        Dictionary: Query response.
    """
    return prometheus_query(prometheus=prometheus, query="/api/v1/alerts")


def get_hco_cr_modification_alert_state(prometheus, component_name):
    """This function will check the 'KubevirtHyperconvergedClusterOperatorCRModification'
    an alert generated after the 'kubevirt_hco_out_of_band_modifications_count' metrics triggered.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.

    Returns:
        String: State of the 'KubevirtHyperconvergedClusterOperatorCRModification' alert.
    """

    # Find an alert "KubevirtHyperconvergedClusterOperatorCRModification" and return it's state.
    def _get_state():
        for alert in get_all_prometheus_alerts(prometheus=prometheus)["data"].get(
            "alerts", []
        ):
            if (
                alert["labels"]["alertname"] == KUBEVIRT_CR_ALERT_NAME
                and component_name == alert["labels"]["component_name"]
            ):
                return alert.get("state")

    # Alert is not generated immediately. Wait for 30 seconds.
    samples = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=_get_state,
    )
    for alert_state in samples:
        if alert_state:
            return alert_state


def get_all_hco_cr_modification_alert(prometheus):
    """Function returns existing "KubevirtHyperconvergedClusterOperatorCRModification" alerts.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.

    Returns:
        List: Contains 'KubevirtHyperconvergedClusterOperatorCRModification' alerts.
    """
    # Find how many "KubevirtHyperconvergedClusterOperatorCRModification" alert are present.
    present_alerts = []
    for alert in get_all_prometheus_alerts(prometheus=prometheus)["data"].get(
        "alerts", []
    ):
        if alert["labels"]["alertname"] == KUBEVIRT_CR_ALERT_NAME:
            present_alerts.append(alert)
    return present_alerts
