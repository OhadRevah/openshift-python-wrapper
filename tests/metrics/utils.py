import logging
import re
from collections import defaultdict

from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_5MIN
from utilities.virt import VirtualMachineForTests, fedora_vm_body


LOGGER = logging.getLogger(__name__)
KUBEVIRT_CR_ALERT_NAME = "KubevirtHyperconvergedClusterOperatorCRModification"
CURL_QUERY = "curl -k https://localhost:8443/metrics"
NUM_TEST_VMS = 3


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


def get_query_result(prometheus, query, timeout=TIMEOUT_5MIN):
    """
    Performs Prometheus query, waits for the results to show up, returns the query results

    Args:
        prometheus (Prometheus Object): Prometheus object.
        query (str): Prometheus query string (for strings with special characters they need to be parsed by the
        caller)
        timeout: (Int): Timeout value in seconds

    Returns:
        list: List of query results
    """
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=get_metric_by_prometheus_query,
        prometheus=prometheus,
        query=query,
    )
    try:
        for sample in sampler:
            if sample["data"]["result"]:
                return sample["data"]["result"]
    except TimeoutExpiredError:
        LOGGER.error(f'No vm(s) found via prometheus query: "{query}"')
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


def get_vm_names_from_metric(prometheus, query, timeout=TIMEOUT_5MIN):
    """
    Retrieves a list of vm names from a given prometheus api query result

    Args:
        prometheus (Prometheus Object): Prometheus object.
        query (str): Prometheus query string (for strings with special characters they need to be parsed by the
        caller)
        timeout: (Int): Timeout value in seconds

    Returns:
        list: List of vm names that are present in the query result
    """
    result = get_query_result(prometheus=prometheus, query=query, timeout=timeout)
    return [name.get("metric").get("name") for name in result]


def parse_vm_metric_results(raw_output):
    """
    Parse metrics received from virt-handler pod

    Args:
        raw_output (str): raw metric output received from virt-handler pods

    Returns:
        dict: Dictionary of parsed output
    """
    regex_metrics = r"(?P<metric>\S+)\{(?P<labels>[^\}]+)\}[ ](?P<value>\d+)"
    metric_results = {}
    for line in raw_output.splitlines():
        if line.startswith("# HELP"):
            metric, description = line[7:].split(" ", 1)
            metric_results.setdefault(metric, {})["help"] = description
        elif line.startswith("# TYPE"):
            metric, metric_type = line[7:].split(" ", 1)
            metric_results.setdefault(metric, {})["type"] = metric_type
        elif re.match(regex_metrics, line):
            metric_instance_dict = re.match(regex_metrics, line).groupdict()
            metric_instance_dict["labeldict"] = {
                val[0]: val[-1]
                for val in [
                    label.partition("=")
                    for label in metric_instance_dict["labels"].split(",")
                ]
            }
            metric_results.setdefault(metric_instance_dict["metric"], {}).setdefault(
                "results", []
            ).append(metric_instance_dict)
        else:
            metric, metric_type = line.split(" ", 1)
            metric_results.setdefault(metric, {})["type"] = metric_type
    return metric_results


def assert_vm_metric_virt_handler_pod(query, vm):
    """
    Get vm metric information from virt-handler pod

    Args:
        query (str): Prometheus query string
        vm (VirtualMachineForTests): A VirtualMachineForTests

    """
    pod = vm.vmi.virt_handler_pod
    output = parse_vm_metric_results(
        raw_output=pod.execute(command=["bash", "-c", f"{CURL_QUERY}"])
    )
    assert (
        output
    ), f'No query output found from virt-handler pod "{pod.name}" for query: "{CURL_QUERY}"'
    metrics_list = []
    if query in output:
        metrics_list = [
            result["labeldict"]
            for result in output[query]["results"]
            if "labeldict" in result and vm.name in result["labeldict"]["name"]
        ]
    assert metrics_list, (
        f'Virt-handler pod query:"{CURL_QUERY}" did not return any vm metric information for vm: {vm.name} '
        f"from virt-handler pod: {pod.name}. "
    )
    assert_validate_vm_metric(vm=vm, metrics_list=metrics_list)


def assert_validate_vm_metric(vm, metrics_list):
    """
    Validate vm metric information fetched from virt-handler pod

    Args:
        vm (VirtualMachineForTests): A VirtualMachineForTests
        metrics_list (list): List of metrics entries collected from associated Virt-handler pod

    """
    expected_values = {
        "kubernetes_vmi_label_kubevirt_io_nodeName": vm.vmi.node.name,
        "namespace": vm.namespace,
        "node": vm.vmi.node.name,
    }
    LOGGER.info(
        f"Virt-handler pod metrics associated with vm: {vm.name} are: {metrics_list}"
    )
    metric_data_mismatch = [
        entity
        for key in expected_values
        for entity in metrics_list
        if not entity.get(key, None) or expected_values[key] not in entity[key]
    ]

    assert not metric_data_mismatch, (
        f"Vm metric validation via virt-handler pod {vm.vmi.virt_handler_pod}"
        f" failed: {metric_data_mismatch}"
    )


def create_vms(name_prefix, namespace_name, vm_count=NUM_TEST_VMS):
    """
     Create n number of fedora vms.

     Args:
         name_prefix (str): prefix to be used to name virtualmachines
         namespace_name (str): Namespace to be used for vm creation
         vm_count (int): Number of vms to be created

    Returns:
        list: List of VirtualMachineForTests
    """
    vms_list = []
    for idx in range(vm_count):
        vm_name = f"{name_prefix}-{idx}"
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace_name,
            body=fedora_vm_body(name=vm_name),
            teardown=False,
            running=True,
            ssh=True,
        ) as vm:
            vms_list.append(vm)
    return vms_list
