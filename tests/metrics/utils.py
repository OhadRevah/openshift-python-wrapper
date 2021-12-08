import logging
import re
import shlex
import urllib
from collections import Counter, defaultdict

from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_8MIN,
    TIMEOUT_10MIN,
)
from utilities.infra import ExecCommandOnPod, run_ssh_commands
from utilities.network import assert_ping_successful
from utilities.virt import VirtualMachineForTests, fedora_vm_body


LOGGER = logging.getLogger(__name__)
KUBEVIRT_CR_ALERT_NAME = "KubevirtHyperconvergedClusterOperatorCRModification"
CURL_QUERY = "curl -k https://localhost:8443/metrics"
NUM_TEST_VMS = 3
PING = "ping"
VIRT_HANDLER_CONTAINER = "virt-handler"
JOB_NAME = "kubevirt-prometheus-metrics"
TOPK_VMS = 3
MIN_NUM_VM = 1
SWAP_NAME = "myswap"
SWAP_ENABLE_COMMANDS = [
    f"sudo dd if=/dev/zero of=/{SWAP_NAME} bs=1M count=1000",
    f"sudo chmod 600 /{SWAP_NAME}",
    f"sudo mkswap /{SWAP_NAME}",
    f"sudo swapon /{SWAP_NAME}",
    "sudo sysctl vm.swappiness=100",
]
VALIDATE_SWAP_ON = "swapon -s"


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

    response = prometheus_query(prometheus=prometheus, query=query)
    LOGGER.info(f"Prometheus query: {query}, response: {response}")
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
        wait_timeout=TIMEOUT_10MIN,
        sleep=10,
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


def get_vm_metrics(prometheus, query, vm_name, timeout=TIMEOUT_5MIN):
    """
    Performs Prometheus query, waits for the expected vm related metrics to show up in results,
    returns the query results

    Args:
        prometheus(Prometheus Object): Prometheus object.
        query(str): Prometheus query string (for strings with special characters they need to be parsed by the
        caller)
        vm_name(str): name of the vm to look for in prometheus query results
        timeout(int): Timeout value in seconds

    Returns:
        list: List of query results if appropriate vm name is found in the results.

    Raise:
        TimeoutExpiredError: if a given vm name does not show up in prometheus query results

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
            data_result = sample["data"]["result"]
            if data_result and vm_name in [
                name.get("metric").get("name") for name in data_result
            ]:
                return data_result
    except TimeoutExpiredError:
        LOGGER.error(
            f'vm {vm_name} not found via prometheus query: "{query}" result: {data_result}'
        )
        raise


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
        for alert in prometheus.alerts["data"].get("alerts", []):
            if (
                alert["labels"]["alertname"] == KUBEVIRT_CR_ALERT_NAME
                and component_name == alert["labels"]["component_name"]
            ):
                return alert.get("state")

    # Alert is not generated immediately. Wait for 30 seconds.
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=_get_state,
    )
    for alert_state in samples:
        if alert_state:
            return alert_state


def get_hco_cr_modification_alert_summary_with_count(prometheus, component_name):
    """This function will check the 'KubevirtHyperconvergedClusterOperatorCRModification'
    an alert summary generated after the 'kubevirt_hco_out_of_band_modifications_count' metrics triggered.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.

    Returns:
        String: Summary of the 'KubevirtHyperconvergedClusterOperatorCRModification' alert contains count.

        example:
        Alert summary for single change:
        "1 out-of-band CR modifications were detected in the last 10 minutes."
    """

    # Find an alert "KubevirtHyperconvergedClusterOperatorCRModification" and return it's summary.
    def _get_summary():
        for alert in prometheus.alerts["data"].get("alerts", []):
            if (
                alert["labels"]["alertname"] == KUBEVIRT_CR_ALERT_NAME
                and component_name == alert["labels"]["component_name"]
            ):
                return alert.get("annotations", {}).get("summary")

    # Alert is not updated immediately. Wait for 300 seconds.
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=2,
        func=_get_summary,
    )
    try:
        for alert_summary in samples:
            if alert_summary is not None:
                return alert_summary
    except TimeoutError:
        LOGGER.error(f"Summary is not present for Alert {KUBEVIRT_CR_ALERT_NAME}")


def get_all_hco_cr_modification_alert(prometheus):
    """Function returns existing "KubevirtHyperconvergedClusterOperatorCRModification" alerts.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.

    Returns:
        List: Contains 'KubevirtHyperconvergedClusterOperatorCRModification' alerts.
    """
    # Find how many "KubevirtHyperconvergedClusterOperatorCRModification" alert are present.
    present_alerts = []
    for alert in prometheus.alerts["data"].get("alerts", []):
        if alert["labels"]["alertname"] == KUBEVIRT_CR_ALERT_NAME:
            present_alerts.append(alert)
    return present_alerts


def wait_for_summary_count_to_be_expected(
    prometheus, component_name, expected_summary_value
):
    """This function will wait for the expected summary to match with
    the summary message from component specific alert.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.
        component_name (String): Name of the component.
        expected_summary_value (Integer): Expected value of the component after update.

    Returns:
        String: It will return the Summary of the component once it matches to the expected_summary.

        example:
        Alert summary for 3 times change in component:
        "3 out-of-band CR modifications were detected in the last 10 minutes."
    """

    def extract_value_from_message(message):
        mo = re.search(
            pattern=r"(?P<count>\d+) out-of-band CR modifications were detected in the last (?P<time>\d+) minutes.",
            string=message,
        )
        assert mo, f"message is not expected format: {message}"
        match_dict = mo.groupdict()
        return int(match_dict["count"])

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=5,
        func=get_hco_cr_modification_alert_summary_with_count,
        prometheus=prometheus,
        component_name=component_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                value = extract_value_from_message(message=sample)
                if value == expected_summary_value:
                    return value
    except TimeoutError:
        LOGGER.error(
            f"Summary count did not update for component {component_name}: "
            f"current={sample} expected={expected_summary_value}"
        )
        raise


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


def create_vms(name_prefix, namespace_name, vm_count=NUM_TEST_VMS, client=None):
    """
    Create n number of fedora vms.

    Args:
        name_prefix (str): prefix to be used to name virtualmachines
        namespace_name (str): Namespace to be used for vm creation
        vm_count (int): Number of vms to be created
        client (DynamicClient): DynamicClient object

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
            client=client,
        ) as vm:
            vms_list.append(vm)
    return vms_list


def get_topk_query(metric_names, time_period="5m"):
    """
    Creates a topk query string based on metric_name

    Args:
        metric_names (list): list of strings

        time_period (str): indicates the time period over which top resources would be considered

    Returns:
        str: query string to be used for the topk query
    """
    query_parts = [
        f" sum by (name, namespace) (rate({metric}[{time_period}]))"
        for metric in metric_names
    ]
    return f"topk(3, {(' + ').join(query_parts)})"


def assert_topk_vms(prometheus, query, vm_list, timeout=TIMEOUT_8MIN):
    """
    Performs a topk query against prometheus api, waits until it has expected result entries and returns the
    results

    Args:
        prometheus (Prometheus Object): Prometheus object.
        query (str): Prometheus query string
        vm_list (list): list of vms to show up in topk results
        timeout (int): Timeout value in seconds

    Returns:
        list: List of results

    Raises:
        TimeoutExpiredError: on mismatch between number of vms founds in topk query results vs expected number of vms
    """
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=get_metric_by_prometheus_query,
        prometheus=prometheus,
        query=urllib.parse.quote_plus(query),
    )
    sample = None
    try:
        for sample in sampler:
            data_sample = sample["data"]["result"]
            if len(data_sample) == len(vm_list):
                vms_found = [
                    entry["metric"]["name"]
                    for entry in data_sample
                    if entry.get("metric", {}).get("name") in vm_list
                ]
                if Counter(vms_found) == Counter(vm_list):
                    return data_sample
    except TimeoutExpiredError:
        LOGGER.error(
            f'Expected vms: "{vm_list}" for prometheus query:'
            f' "{query}" does not match with actual results: {sample} after {timeout} seconds.'
        )
        raise


def run_vm_commands(vms, commands):
    """
    This helper function, runs commands on vms to generate metrics.
    Args:
        vms (list): List of VirtualMachineForTests
        commands (list): Used to execute commands against nodes (where created vms are scheduled)

    """
    commands = [shlex.split(command) for command in commands]
    LOGGER.info(f"Commands: {commands}")
    for vm in vms:
        if any(command[0].startswith("ping") for command in commands):
            assert_ping_successful(
                src_vm=vm, dst_ip="localhost", packet_size=10000, count=20
            )
        else:
            run_ssh_commands(host=vm.ssh_exec, commands=commands)


def run_node_command(vms, command, utility_pods):
    """
    This is a helper function to run a command against a node associated with a given virtual machine, to prepare
    it for metric generation commands.

    Args:
        vms: (List): List of VirtualMachineForTests objects
        utility_pods (list): Utility pods
        command (str): Command to be run against a given node

    Raise:
        Asserts on command execution failure
    """
    # If multiple vms are placed on the same node, we only want to run command against the node once.
    # So we need to collect the node names first
    node_names = []
    for vm in vms:
        node_name = vm.vmi.node.name
        LOGGER.info(f"For vm {vm.name} is placed on node: {node_name}")
        if node_name not in node_names:
            node_names.append(node_name)
    for node_name in node_names:
        LOGGER.info(f'Running command "{command}" on node {node_name}')
        ExecCommandOnPod(utility_pods=utility_pods, node=node_name).exec(
            command=command
        )


def assert_prometheus_metric_values(prometheus, query, vm, timeout=TIMEOUT_5MIN):
    """
    Compares metric query result with expected values

    Args:
        prometheus (Prometheus Object): Prometheus object.
        query (str): Prometheus query string
        vm (VirtualMachineForTests): Vm that is expected to show up in Prometheus query results
        timeout (int): Timeout value in seconds

    Raise:
        Asserts on premetheus results not matching expected result
    """
    results = get_vm_metrics(
        prometheus=prometheus, query=query, vm_name=vm.name, timeout=timeout
    )
    result_entry = [
        result["metric"]
        for result in results
        if result.get("metric") and result["metric"]["name"] == vm.name
    ]

    assert result_entry is not None, (
        f'Prometheus query: "{query}" result: {results} does not include expected vm: '
        f"{vm.name}"
    )

    expected_result = {
        "job": JOB_NAME,
        "service": JOB_NAME,
        "container": VIRT_HANDLER_CONTAINER,
        "kubernetes_vmi_label_kubevirt_io_vm": vm.name,
        "kubernetes_vmi_label_kubevirt_io_nodeName": vm.vmi.node.name,
        "namespace": vm.namespace,
        "pod": vm.vmi.virt_handler_pod,
    }
    metric_value_mismatch = [
        {key: result.get(key, "")}
        for result in result_entry
        for key in expected_result
        if not result.get(key, "") or result[key] != expected_result[key]
    ]
    assert metric_value_mismatch, (
        f"For Prometheus query {query} data validation failed for: "
        f"{metric_value_mismatch}"
    )


def enable_swap_fedora_vm(vm):
    """
    Enable swap on on fedora vms

    Args:
       vm (VirtualMachineForTests): a VirtualMachineForTests, on which swap is to be enabled

    Raise:
        Asserts if swap memory is not enabled on a given vm
    """
    commands = [shlex.split(command) for command in SWAP_ENABLE_COMMANDS]
    run_ssh_commands(host=vm.ssh_exec, commands=commands)
    out = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split(VALIDATE_SWAP_ON))
    assert SWAP_NAME not in out, f"Unable to enable swap on vm: {vm.name}: {out}"


def get_vmi_phase_count(prometheus, os_name, flavor, workload, query):
    """
    Get the metric from the defined Prometheus query

    Args:
        prometheus (Prometheus object): Prometheus object to interact with the query
        os_name (str): the OS name as it appears on Prometheus, e.g. windows19
        flavor (str): the flavor as it appears on Prometheus, e.g. tiny
        workload (str): the type of the workload on the VM, e.g. server
        query (str): query str to use according to the query_dict

    Returns:
        the metric value
    """
    query = query.format(os_name=os_name, flavor=flavor, workload=workload)
    LOGGER.debug(f"query for prometheus: query={query}")
    response = get_metric_by_prometheus_query(prometheus=prometheus, query=query)

    if not response["data"]["result"]:
        return 0

    return int(response["data"]["result"][0]["value"][1])


def wait_until_kubevirt_vmi_phase_count_is_expected(
    prometheus, vmi_annotations, expected, query
):
    os_name = vmi_annotations[Template.VMAnnotations.OS]
    flavor = vmi_annotations[Template.VMAnnotations.FLAVOR]
    workload = vmi_annotations[Template.VMAnnotations.WORKLOAD]
    LOGGER.info(
        f"Waiting for kubevirt_vmi_phase_count: expected={expected} os={os_name} flavor={flavor} workload={workload}"
    )
    query_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=3,
        func=get_vmi_phase_count,
        prometheus=prometheus,
        os_name=os_name,
        flavor=flavor,
        workload=workload,
        query=query,
    )
    sample = None
    try:
        for sample in query_sampler:
            if sample == expected:
                return True
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout exception while waiting for a specific value from query: current={sample} expected={expected}"
        )
        raise


def get_prometheus_monitoring_pods(admin_client):
    """
    Get all Prometheus pods within the openshift-monitoring namespace

    Args:
        admin_client (DynamicClient): DynamicClient object

    Returns:
        list: list of all prometheus pods within the openshift-monitoring namespace
    """
    prometheus_pods_monitoring_namespace_list = list(
        Pod.get(
            dyn_client=admin_client,
            namespace="openshift-monitoring",
            label_selector=(
                (
                    f"{Resource.ApiGroup.APP_KUBERNETES_IO}/name in "
                    "(prometheus-operator, prometheus, prometheus-adapter)"
                )
            ),
        )
    )
    assert (
        prometheus_pods_monitoring_namespace_list
    ), "no matching pods found on the cluster"
    return prometheus_pods_monitoring_namespace_list


def get_not_running_prometheus_pods(admin_client):
    """
    Get all Prometheus pods that are not in Running status

    Args:
        admin_client (DynamicClient): DynamicClient object

    Returns:
        dict: dict of prometheus pods' name (key) and status (value) that are not in Running status
    """
    prometheus_pods_monitoring_namespace_list = get_prometheus_monitoring_pods(
        admin_client=admin_client
    )
    return {
        pod.name: pod.status
        for pod in prometheus_pods_monitoring_namespace_list
        if pod.status != Pod.Status.RUNNING
    }


def get_vm_vcpu_cpu_info_from_prometheus(prometheus, query):
    """Gets vcpu and cpu information from the metrics of specific VM.

    Args:
        prometheus (Prometheus): Prometheus object
        query (str): query str to use according to the query_dict

    Returns:
        dict: It contains dictionary of 'vcpu_cpu and it's value'.
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=2,
        func=get_metric_by_prometheus_query,
        prometheus=prometheus,
        query=query,
    )
    sample = None
    try:
        for sample in samples:
            result = sample["data"].get("result")
            if result:
                return [
                    vcpu_keys
                    for vcpu_keys, vcpu_values in result[0].get("metric").items()
                    if vcpu_keys.startswith("vcpu") and vcpu_values == "true"
                ]
    except TimeoutExpiredError:
        LOGGER.error(
            f"Failed to get data from query '{query}' in time. Current data: {sample}"
        )
        raise


def validate_vm_vcpu_cpu_affinity_with_prometheus(prometheus, nodes, query, vm):
    """
    This will check the 'vcpu_cpu' count of running VM with node CPU count on which VM placed.

    Args:
        prometheus (Prometheus object): Prometheus object
        nodes (list): List of nodes objects
        query (str): Prometheus query string
        vm (VirtaulMachine): a VirtualMachineForTests object

    Raises:
        AssertionError: If CPU count from VM not matches with Prometheus metrics output.
    """
    cpu = vm.instance.spec.template.spec.domain.cpu
    cpu_count_from_vm = (cpu.threads or 1) * (cpu.cores or 1) * (cpu.sockets or 1)

    cpu_info_from_prometheus = get_vm_vcpu_cpu_info_from_prometheus(
        prometheus=prometheus,
        query=urllib.parse.quote_plus(query),
    )

    cpu_count_from_node = [
        int(vm.vmi.node.instance.status.capacity.cpu)
        for node in nodes
        if node.name == vm.vmi.node.name
    ][0]
    LOGGER.info(f"Cpu count from node {vm.vmi.node.name}: {cpu_count_from_node}")

    if cpu_count_from_vm > 1:
        cpu_count_from_node = cpu_count_from_node * cpu_count_from_vm

    assert cpu_count_from_node == len(cpu_info_from_prometheus), (
        f"Actual CPU count {cpu_count_from_node} not matching with "
        f"expected CPU count {len(cpu_info_from_prometheus)} for VM CPU {cpu_count_from_vm}"
    )
