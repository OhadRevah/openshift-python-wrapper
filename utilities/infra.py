import ast
import base64
import importlib
import json
import logging
import os
import re
import shlex
import shutil
from configparser import ConfigParser
from contextlib import contextmanager
from pathlib import Path

import bugzilla
import kubernetes
import netaddr
import paramiko
import pytest
import requests
from jira import JIRA
from kubernetes.client import ApiException
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.daemonset import DaemonSet
from ocp_resources.namespace import Namespace
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.project import Project, ProjectRequest
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.service import Service
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from pytest_testconfig import config as py_config

from utilities.constants import (
    PODS_TO_COLLECT_INFO,
    SANITY_TESTS_FAILURE,
    TIMEOUT_2MIN,
    TIMEOUT_10MIN,
)
from utilities.exceptions import CommandExecFailed, UtilityPodNotFoundError


BUG_STATUS_CLOSED = ("VERIFIED", "ON_QA", "CLOSED", "RELEASE_PENDING")
JIRA_STATUS_CLOSED = ("closed", "done", "obsolete", "resolved")
NON_EXIST_URL = "https://noneexist.com"
EXCLUDED_FROM_URL_VALIDATION = ("", NON_EXIST_URL)
INTERNAL_HTTP_SERVER_ADDRESS = "internal-http.kube-system"
HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT = {
    "kubevirt": {
        "api_group_prefix": "kubevirt",
        "config": "configuration",
    },
    "cdi": {
        "api_group_prefix": "containerizeddataimporter",
        "config": "config",
    },
}


LOGGER = logging.getLogger(__name__)


class OsDictNotFoundError(Exception):
    pass


class ClusterSanityError(Exception):
    def __init__(self, err_str):
        self.err_str = err_str

    def __str__(self):
        return self.err_str


def label_project(name, label, admin_client):
    ns = Namespace(client=admin_client, name=name)
    ResourceEditor({ns: {"metadata": {"labels": label}}}).update()


def create_ns(name, unprivileged_client=None, kmp_vm_label=None, admin_client=None):
    """
    For kubemacpool labeling opt-modes, provide kmp_vm_label and admin_client as admin_client
    """
    if not unprivileged_client:
        with Namespace(client=admin_client, name=name, label=kmp_vm_label) as ns:
            ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
            yield ns
    else:
        with ProjectRequest(name=name, client=unprivileged_client):
            project = Project(name=name, client=unprivileged_client)
            project.wait_for_status(project.Status.ACTIVE, timeout=TIMEOUT_2MIN)
            if kmp_vm_label:
                label_project(name=name, label=kmp_vm_label, admin_client=admin_client)
            yield project


def get_cert(server_type):
    path = os.path.join("tests/storage/cdi_import", py_config["servers"][server_type])
    with open(path, "r") as cert_content:
        data = cert_content.read()
    return data


class ClusterHosts:
    class Type:
        VIRTUAL = "virtual"
        PHYSICAL = "physical"


class MissingResourceException(Exception):
    def __init__(self, resource):
        self.resource = resource

    def __str__(self):
        return f"No resources of type {self.resource} were found. Please check the test environment setup."


class UrlNotFoundError(Exception):
    def __init__(self, url_request):
        self.url_request = url_request

    def __str__(self):
        return f"{self.url_request.url} not found. status code is: {self.url_request.status_code}"


class FileNotFoundInUrlError(Exception):
    def __init__(self, url_request, file_name):
        self.url_request = url_request
        self.file_name = file_name

    def __str__(self):
        return f"{self.file_name} not found in url {self.url_request.url}"


def validate_file_exists_in_url(url):
    base_url, file_name = url.rsplit("/", 1)
    response = requests.get(base_url, verify=False)
    if response.status_code != 200:
        raise UrlNotFoundError(url_request=response)

    if file_name not in str(response.content):
        raise FileNotFoundInUrlError(url_request=response, file_name=file_name)


def url_excluded_from_validation(url):
    # Negative URL test cases or internal http server
    return url in EXCLUDED_FROM_URL_VALIDATION or INTERNAL_HTTP_SERVER_ADDRESS in url


def get_schedulable_nodes_ips(nodes):
    return {node.name: node.internal_ip for node in nodes}


def camelcase_to_mixedcase(camelcase_str):
    # Utility to convert CamelCase to mixedCase
    # Example: Service type may be NodePort but in VM attributes.spec.ports it is nodePort
    return camelcase_str[0].lower() + camelcase_str[1:]


def get_admin_client():
    return DynamicClient(client=kubernetes.config.new_client_from_config())


def get_pod_by_name_prefix(dyn_client, pod_prefix, namespace, get_all=False):
    """
    Args:
        dyn_client (DynamicClient): OCP Client to use.
        pod_prefix (str): str or regex pattern.
        namespace (str): Namespace name.
        get_all (bool): Return all pods if True else only the first one.

    Returns:
        list or Pod: A list of all matching pods if get_all (empty list if no pods found) else only the first pod.
    """
    pods = [
        pod
        for pod in Pod.get(dyn_client=dyn_client, namespace=namespace)
        if re.match(pod_prefix, pod.name)
    ]
    if get_all:
        return pods  # Some negative cases check if no pods exists.
    elif pods:
        return pods[0]
    raise NotFoundError(f"A pod with the {pod_prefix} prefix does not exist")


def run_ssh_commands(host, commands):
    """
    Run commands via SSH

    Args:
        host (Host): rrmngmnt host to execute the commands from.
        commands (list): List of multiple command lists [[cmd1, cmd2, cmd3]] or a list with a single command [cmd]
        Examples:
             ["sudo", "reboot"], [["sleep", "5"], ["date"]]

    Returns:
        list: List of commands output.

    Raise:
        CommandExecFailed: If command failed to execute.
    """
    results = []
    commands = commands if isinstance(commands[0], list) else [commands]
    with host.executor().session() as ssh_session:
        for cmd in commands:
            rc, out, err = ssh_session.run_cmd(cmd=cmd)
            LOGGER.info(f"[SSH][{host.fqdn}] Executed: {' '.join(cmd)}")
            if rc:
                raise CommandExecFailed(name=cmd, err=err)

            results.append(out)

    return results


def prepare_test_dir_log(item, prefix, logs_path):
    test_cls_name = item.cls.__name__ if item.cls else ""
    test_dir_log = os.path.join(
        logs_path,
        item.fspath.dirname.split("/tests/")[-1],
        item.fspath.basename.partition(".py")[0],
        test_cls_name,
        item.name,
        prefix,
    )
    os.environ["TEST_DIR_LOG"] = test_dir_log
    os.makedirs(test_dir_log, exist_ok=True)


def prepare_test_dir_log_utilities():
    """
    prepares a utilities directory under the base log collection dir

    This is used in the case that log collection is requested outside the scope of a test
    (for example, during debugging)

    Returns:
        str: TEST_DIR_LOG (the base directory for log collection)
    """
    test_dir_log = os.path.join(
        os.environ.get("CNV_TEST_COLLECT_BASE_DIR"),
        "utilities",
    )
    os.environ["TEST_DIR_LOG"] = test_dir_log
    os.makedirs(test_dir_log, exist_ok=True)
    return test_dir_log


def collect_logs_prepare_test_dir():
    """
    Provides and ensures the creation of a directory to collect logs

    If this runs in the scope of a test the directory path structure will include the test node path
    If this is run outside the scope of a test the directory path will be for utilities

    Returns:
        str: test_dir (the directory prefixed for collecting logs)
    """
    test_dir = os.environ.get("TEST_DIR_LOG")
    if not test_dir:
        # log collection was requested outside the scope of a test
        test_dir = prepare_test_dir_log_utilities()
    os.makedirs(test_dir, exist_ok=True)
    return test_dir


def collect_logs_prepare_pods_dir():
    """
    Provides and ensures the creation of a directory to collect pod logs

    This will prepare the directory under the directory created by collect_logs_prepare_test_dir

    Returns:
        str: pods_dir (directory to save pod logs)
    """
    test_dir = collect_logs_prepare_test_dir()
    pods_dir = os.path.join(test_dir, "Pods")
    os.makedirs(pods_dir, exist_ok=True)
    return pods_dir


def collect_logs_resources(resources_to_collect, namespace_name=None):
    get_kwargs = {"dyn_client": get_admin_client()}
    test_dir = collect_logs_prepare_test_dir()
    for _resources in resources_to_collect:
        resource_dir = os.path.join(test_dir, _resources.__name__)

        if _resources == Service:
            get_kwargs["namespace"] = namespace_name

        for resource_obj in _resources.get(**get_kwargs):
            if not os.path.isdir(resource_dir):
                os.makedirs(resource_dir, exist_ok=True)

            with open(
                os.path.join(resource_dir, f"{resource_obj.name}.yaml"), "w"
            ) as fd:
                fd.write(resource_obj.instance.to_str())


def collect_logs_pods(pods):
    pods_dir = collect_logs_prepare_pods_dir()
    for pod in pods:
        kwargs = {}
        for pod_prefix in PODS_TO_COLLECT_INFO:
            if pod.name.startswith(pod_prefix):
                if pod_prefix == "virt-launcher":
                    kwargs = {"container": "compute"}

                with open(os.path.join(pods_dir, f"{pod.name}.log"), "w") as fd:
                    fd.write(pod.log(**kwargs))

                with open(os.path.join(pods_dir, f"{pod.name}.yaml"), "w") as fd:
                    fd.write(pod.instance.to_str())


def generate_namespace_name(file_path):
    return (file_path.strip(".py").replace("/", "-").replace("_", "-"))[-63:].split(
        "-", 1
    )[-1]


def separator(symbol_, val=None):
    terminal_width = shutil.get_terminal_size(fallback=(120, 40))[0]
    if not val:
        return f"{symbol_ * terminal_width}"

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"


def generate_latest_os_dict(os_list):
    """
    Get latest os dict.

    Args:
        os_list (list): [<os-name>]_os_matrix - a list of dicts.

    Returns:
        dict: {Latest OS name: latest supported OS dict} else raises an exception.

    Raises:
        OsDictNotFoundError: If no os matched.
    """
    for os_dict in os_list:
        for os_version, os_values in os_dict.items():
            if os_values.get("latest"):
                return {os_version: os_values}

    raise OsDictNotFoundError(f"No OS is marked as 'latest': {os_list}")


def get_latest_os_dict_list(os_list):
    """
    Get latest os dict generated by 'generate_latest_os_dict()'
    This will extract the dict from `generate_latest_os_dict()` without the name key.

    Args:
        os_list (list): [rhel|windows|fedora]_os_matrix - a list of dicts

    Returns:
        list: List of oses dict [{latest supported OS dict}]
    """
    res = []
    for _os in os_list:
        res.append(list(generate_latest_os_dict(os_list=_os).values())[0])
    return res


def base64_encode_str(text):
    return base64.b64encode(text.encode()).decode()


def hco_cr_jsonpatch_annotations_dict(component, path, value, op="add"):
    # https://github.com/kubevirt/hyperconverged-cluster-operator/blob/master/docs/cluster-configuration.md#jsonpatch-annotations
    component_dict = HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT[component]

    return {
        "metadata": {
            "annotations": {
                f"{component_dict['api_group_prefix']}.{Resource.ApiGroup.KUBEVIRT_IO}/jsonpatch": json.dumps(
                    [
                        {
                            "op": op,
                            "path": f"/spec/{component_dict['config']}/{path}",
                            "value": value,
                        }
                    ]
                )
            }
        }
    }


def private_to_public_key(key):
    return paramiko.RSAKey.from_private_key_file(key).get_base64()


def name_prefix(name):
    return name.split(".")[0]


def authorized_key(private_key_path):
    return f"ssh-rsa {private_to_public_key(key=private_key_path)} root@exec1.rdocloud"


def get_connection_params(conf_file_name):
    conf_file = os.path.join(Path(".").resolve(), conf_file_name)
    parser = ConfigParser()
    # Open the file with the correct encoding
    parser.read(conf_file, encoding="utf-8")
    params_dict = {}
    for params in parser.items("DEFAULT"):
        params_dict[params[0]] = params[1]
    return params_dict


def get_bug_status(bug):
    bugzilla_connection_params = get_connection_params(conf_file_name="bugzilla.cfg")
    bzapi = bugzilla.Bugzilla(
        url=bugzilla_connection_params["bugzilla_url"],
        user=bugzilla_connection_params["bugzilla_username"],
        api_key=bugzilla_connection_params["bugzilla_api_key"],
    )
    return bzapi.getbug(objid=bug).status


def get_jira_connection_params():
    return get_connection_params(conf_file_name="jira.cfg")


def get_jira_status(jira_connection_params, jira):
    jira_connection = JIRA(
        basic_auth=(
            jira_connection_params["username"],
            jira_connection_params["password"],
        ),
        options={"server": jira_connection_params["url"]},
    )
    return jira_connection.issue(id=jira).fields.status.name


def collect_logs():
    """
    This will check if the log collector is enabled for this session

    Checks the value in the py_config which is configured according to the global config of the current session
    This can also be explicitly enabled using --log-collector flag when running pytest

    Returns
        bool: log collector is enabled for the session
    """
    return py_config.get("log_collector", False)


def collect_resources_for_test(resources_to_collect, namespace_name=None):
    """
    This will collect all current resources matching the type(s) specified in the list of resources_to_collect

    A convenient function to explicitly collect certain resources
    simplified so it can be used from within a test case,
    probably you will want to use this during exception handling when a test fails
    ie: in order to collect resources that otherwise are not collected as part of the resource collection.

    Args:
        resources_to_collect (list): list of Resource object classes to collect
        namespace_name (string): (optional) the namespace to use
    """
    try:
        collect_logs_resources(
            resources_to_collect=resources_to_collect,
            namespace_name=namespace_name,
        )
    except Exception as exp:
        LOGGER.debug(
            f"Failed to collect resource for test: {resources_to_collect} {exp}"
        )


def write_to_extras_file(extras_file_name, content, extra_dir_name="extras"):
    """
    This will write to a file that will be available after the test execution,

    A convenient function to explicitly collect certain information from a test
    simplified so it can be used from within a test case,
    probably you will want to use this to write information that is not suitable for logging
     either due to the information being too long for the logs or not human readable or valuable as a log

    this is a way to store information useful for debugging or analysis which will persist after the execution/cluster

    Args:
        extras_file_name (string): name of the file to write
        content (string): the content of the file to write
        extra_dir_name (string): (optional) the directory name to create inside the test collect dir
    """
    test_dir = collect_logs_prepare_test_dir()
    extras_dir = os.path.join(test_dir, extra_dir_name)
    os.makedirs(extras_dir, exist_ok=True)
    extras_file_path = os.path.join(extras_dir, extras_file_name)
    try:
        with open(extras_file_path, "w") as fd:
            fd.write(content)
    except Exception as exp:
        LOGGER.debug(f"Failed to write extras to file: {extras_file_path} {exp}")


def get_pods(dyn_client, namespace, label=None):
    return list(
        Pod.get(
            dyn_client=dyn_client,
            namespace=namespace.name,
            label_selector=label,
        )
    )


def wait_for_pods_deletion(pods):
    for pod in pods:
        pod.wait_deleted()


def validate_nodes_ready(nodes):
    """
    Validates all nodes are in ready

    Args:
         nodes(list): List of Node objects

    Raises:
        AssertionError: Assert on node(s) in not ready state
    """
    not_ready_nodes = [node.name for node in nodes if not node.kubelet_ready]
    if not_ready_nodes:
        raise ClusterSanityError(
            err_str=f"Following nodes are not in ready state: {not_ready_nodes}"
        )


def validate_nodes_schedulable(nodes):
    """
    Validates all nodes are in schedulable state

    Args:
         nodes(list): List of Node objects

    Raises:
        AssertionError: Asserts on node(s) not schedulable
    """
    unschedulable_nodes = [
        node.name for node in nodes if node.instance.spec.unschedulable
    ]
    if unschedulable_nodes:
        raise ClusterSanityError(
            err_str=f"Following nodes are in not unschedulable state: {unschedulable_nodes}"
        )


def wait_for_pods_running(admin_client, namespace, number_of_consecutive_checks=1):
    """
    Waits for all pods in a given namespace to reach Running state. To avoid catching all pods in running state too
    soon, use number_of_consecutive_checks with appropriate values.

    Args:
         admin_client(DynamicClient): Dynamic client
         namespace(Namespace): A namespace object
         number_of_consecutive_checks(int): Number of times to check for all pods in running state
    Raises:
        TimeoutExpiredError: Raises TimeoutExpiredError if any of the pods in the given namespace are not in Running
         state
    """

    def _get_not_running_pods():
        pods = list(Pod.get(dyn_client=admin_client, namespace=namespace.name))
        pods_not_running = []
        for pod in pods:
            try:
                # We should not count any pod that is currently marked for deletion, irrespective of it's
                # current status or a pod that is already in a not running state
                if (
                    pod.instance.metadata.get("deletionTimestamp")
                    or pod.instance.status.phase != pod.Status.RUNNING
                ):
                    pods_not_running.append({pod.name: pod.status})
            except (ResourceNotFoundError, NotFoundError):
                LOGGER.warning(
                    f"Ignoring pod {pod.name} that disappeared during cluster sanity check"
                )
                pods_not_running.append({pod.name: "Deleted"})
        return pods_not_running

    samples = TimeoutSampler(
        wait_timeout=120,
        sleep=1,
        func=_get_not_running_pods,
    )
    sample = None
    try:
        current_check = 0
        for sample in samples:
            if not sample:
                current_check += 1
                if current_check >= number_of_consecutive_checks:
                    return True
            else:
                current_check = 0
    except TimeoutExpiredError as exp:
        raise_multiple_exceptions(
            exceptions=[
                ClusterSanityError(
                    err_str=f"timeout waiting for all pods in namespace {namespace.name} to reach "
                    f"running state, following pods are in not running state: {sample}"
                ),
                exp,
            ]
        )


def get_daemonset_by_name(admin_client, daemonset_name, namespace_name):
    """
    Gets a daemonset object by name

    Args:
        admin_client (DynamicClient): a DynamicClient object
        daemonset_name (str): Name of the daemonset
        namespace_name (str): Name of the associated namespace

    Returns:
        Daemonset: Daemonset object
    """
    for ds in DaemonSet.get(
        dyn_client=admin_client,
        namespace=namespace_name,
        name=daemonset_name,
    ):
        return ds


def wait_for_consistent_resource_conditions(
    dynamic_client,
    hco_namespace,
    expected_conditions,
    resource_kind,
    condition_key1,
    condition_key2,
    total_timeout=TIMEOUT_10MIN,
    polling_interval=5,
    consecutive_checks_count=10,
):
    """This function awaits certain conditions of a given resource_kind (HCO, CSV, etc.).

    Using TimeoutSampler loop and poll the CR (of the resource_kind type) and attempt to match the expected conditions
    against the actual conditions found in the CR.
    Since the conditions statuses might change, we use consecutive checks in order to have consistent results (stable),
    thereby ascertaining that the expected conditions are met over time.

    Args:
        dynamic_client (DynamicClient): admin client
        hco_namespace (Resource): hco_namespace
        expected_conditions (dict): a dict comprises expected conditions to meet, for example:
            {<condition key's value>: <condition key's value>,
            Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,}
        resource_kind (Resource): (e.g. HyperConverged, ClusterServiceVersion)
        condition_key1 (str): the key of the first condition in the actual resource_kind (e.g. type, reason, status)
        condition_key2 (str): the key of the second condition in the actual resource_kind (e.g. type, reason, status)
        total_timeout (int): total timeout to wait for (seconds)
        polling_interval (int): the time to sleep after each iteration (seconds)
        consecutive_checks_count (int): the number of repetitions for the status check to make sure the transition is
        done.
            The default value for this argument is not absolute, and there are situations in which it should be higher
            in order to ascertain the consistency of the Ready status.
            Possible situations:
            1. the resource is in a Ready status, because the process (that should cause
            the change in its state) has not started yet.
            2. some components are in Ready status, but others have not started the process yet.

    Raises:
        TimeoutExpiredError: raised when expected conditions are not met within the timeframe
    """
    samples = TimeoutSampler(
        wait_timeout=total_timeout,
        sleep=polling_interval,
        func=lambda: list(
            resource_kind.get(
                dyn_client=dynamic_client,
                namespace=hco_namespace.name,
            )
        ),
        exceptions_dict={NotFoundError: []},
    )
    current_check = 0
    actual_conditions = {}
    LOGGER.info(
        f"Waiting for resource to stabilize: resource_kind={resource_kind.__name__} conditions={expected_conditions} "
        f"sleep={total_timeout} consecutive_checks_count={consecutive_checks_count}"
    )
    try:
        for sample in samples:
            status_conditions = sample[0].instance.get("status", {}).get("conditions")
            if status_conditions:
                actual_conditions = {
                    condition[condition_key1]: condition[condition_key2]
                    for condition in status_conditions
                    if condition[condition_key1] in expected_conditions
                }
                if actual_conditions == expected_conditions:
                    current_check += 1
                    if current_check >= consecutive_checks_count:
                        return
                else:
                    current_check = 0

    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout expired meeting conditions for resource: resource={resource_kind.kind} "
            f"expected_conditions={expected_conditions} status_conditions={actual_conditions}"
        )
        raise


def raise_multiple_exceptions(exceptions):
    """Raising multiple exceptions

    To be used when multiple exceptions need to be raised, for example when using TimeoutSampler,
    and additional information should be added (so it is viewable in junit report).
    Example:
        except TimeoutExpiredError as exp:
            raise_multiple_exceptions(
                exceptions=[
                    ValueError(f"Error message: {output}"),
                    exp,
                ]
            )

    Args:
        exceptions (list): List of exceptions to be raised. The 1st exception will appear in pytest error message;
                           all exceptions will appear in the stacktrace.

    """
    # After all exceptions were raised
    if not exceptions:
        return
    try:
        raise exceptions.pop()
    finally:
        raise_multiple_exceptions(exceptions=exceptions)


def get_worker_pod(utility_pods, worker_node):
    """
    This function will return a pod based on the node specified as an argument.

    Args:
        utility_pods (list): List of utility pods.
        worker_node (Node ir str): Node to get the pod for it.
    """
    _worker_node_name = (
        worker_node.name if hasattr(worker_node, "name") else worker_node
    )
    for pod in utility_pods:
        if pod.node.name == _worker_node_name:
            return pod


class ExecCommandOnPod:
    def __init__(self, utility_pods, node):
        """
        Run command on pod with chroot /host

        Args:
            utility_pods (list): List of utility pods resources.
            node (Node): Node resource.

        Returns:
            str: Command output
        """
        self.pod = get_worker_pod(utility_pods=utility_pods, worker_node=node)
        if not self.pod:
            raise UtilityPodNotFoundError

    def exec(self, command, ignore_rc=False):
        _command = shlex.split("chroot /host bash -c")
        _command.append(command)
        return self.pod.execute(command=_command, ignore_rc=ignore_rc).strip()

    def get_interface_ip(self, interface):
        out = self.exec(command=f"ip addr show {interface}")
        match_ip = re.search(r"[0-9]+(?:\.[0-9]+){3}", out)
        if match_ip:
            interface_ip = match_ip.group()
            if netaddr.valid_ipv4(interface_ip):
                return interface_ip

    @property
    def reboot(self):
        try:
            self.exec(command="sudo echo b > /proc/sysrq-trigger")
        except ApiException:
            return True
        return False

    @property
    def is_connective(self):
        return self.exec(command="ls")

    def interface_status(self, interface):
        return self.exec(command=f"cat /sys/class/net/{interface}/operstate")

    @property
    def release_info(self):
        out = self.exec(command="cat /etc/os-release")
        release_info = {}
        for line in out.strip().splitlines():
            values = line.split("=", 1)
            if len(values) != 2:
                continue
            release_info[values[0].strip()] = values[1].strip(" \"'")
        return release_info


def cluster_sanity(
    request,
    admin_client,
    cluster_storage_classes,
    nodes,
    hco_namespace,
    junitxml_property=None,
):
    def _storage_sanity_check():
        sc_names = [sc.name for sc in cluster_storage_classes]
        config_sc = list([[*csc][0] for csc in py_config["storage_class_matrix"]])
        exists_sc = [scn for scn in config_sc if scn in sc_names]
        if sorted(config_sc) != sorted(exists_sc):
            raise ClusterSanityError(
                err_str=f"Cluster is missing storage class. Expected {config_sc}, On cluster {exists_sc}\n"
                f"either run with '--storage-class-matrix' or with '{skip_storage_classes_check}'"
            )

    skip_cluster_sanity_check = "--cluster-sanity-skip-check"
    skip_storage_classes_check = "--cluster-sanity-skip-storage-check"
    skip_nodes_check = "--cluster-sanity-skip-nodes-check"
    exceptions_filename = "cluster_sanity_failure.txt"

    if request.session.config.getoption(skip_cluster_sanity_check):
        LOGGER.warning(
            f"Skipping cluster sanity check, got {skip_cluster_sanity_check}"
        )
        return

    LOGGER.info(
        f"Running cluster sanity. (To skip nodes check pass {skip_cluster_sanity_check} to pytest)"
    )
    # Check storage class only if --cluster-sanity-skip-storage-check not passed to pytest.
    if request.session.config.getoption(skip_storage_classes_check):
        LOGGER.warning(
            f"Skipping storage classes check, got {skip_storage_classes_check}"
        )

    else:
        try:
            LOGGER.info(
                f"Check storage classes sanity. (To skip nodes check pass {skip_storage_classes_check} to pytest)"
            )
            _storage_sanity_check()
        except ClusterSanityError as ex:
            exit_pytest_execution(
                filename=exceptions_filename,
                message=ex.err_str,
                junitxml_property=junitxml_property,
            )

    # Check nodes only if --cluster-sanity-skip-nodes-check not passed to pytest.
    if request.session.config.getoption("--cluster-sanity-skip-nodes-check"):
        LOGGER.warning(f"Skipping nodes check, got {skip_nodes_check}")

    else:
        # validate that all the nodes are ready and schedulable and CNV pods are running
        LOGGER.info(
            f"Check nodes sanity. (To skip nodes check pass {skip_nodes_check} to pytest)"
        )
        try:
            validate_nodes_ready(nodes=nodes)
            validate_nodes_schedulable(nodes=nodes)
            wait_for_pods_running(admin_client=admin_client, namespace=hco_namespace)
        except ClusterSanityError as ex:
            exit_pytest_execution(
                filename=exceptions_filename,
                message=ex.err_str,
                junitxml_property=junitxml_property,
            )


@contextmanager
def update_custom_resource(patch, action="update"):
    """Update any CR with given values

    Args:
        patch (dict): dictionary of values that would be used to update a cr. This dict should include the resource
        as the base key
        action (str): type of action to be performed. e.g. "update", "replace" etc.

    Yields:
        dict: {<Resource object>: <backup_as_dict>} or True in case no backup option is selected
    """
    with ResourceEditor(patches=patch, action=action) as edited_source:
        yield edited_source


class ResourceMismatch(Exception):
    pass


def ocp_resources_submodule_files_path():
    """
    Get the list of submodules file path in ocp_resources.
    """
    ignore_files = [
        "utils.py",
        "__init__.py",
        "resource.py",
    ]
    path = importlib.util.find_spec("ocp_resources").submodule_search_locations[0]
    return [
        os.path.join(path, _file)
        for _file in os.listdir(path)
        if _file not in ignore_files
    ]


def get_cluster_resources(admin_client, resource_files_path):
    import ocp_resources  # noqa: F401

    results = []
    exclude_classes = (
        "Resource",
        "NamespacedResource",
        "Event",
        "MTV",
        "UploadTokenRequest",
    )
    exclude_resources_prefix = ("deployer-", "default-", "builder-")
    for _file in resource_files_path:
        with open(_file, "r") as fd:
            tree = ast.parse(source=fd.read())
            for _cls in [cls for cls in tree.body if isinstance(cls, ast.ClassDef)]:
                if _cls.name in exclude_classes:
                    continue

                base_path = f"ocp_resources.{os.path.basename(_file)}"
                resource_path = re.sub(r"\.py$", "", base_path)
                resource_import = importlib.import_module(name=resource_path)
                try:
                    cls_obj = getattr(resource_import, _cls.name)
                    results.extend(
                        [
                            res.name
                            for res in cls_obj.get(dyn_client=admin_client)
                            if not res.name.startswith(exclude_resources_prefix)
                        ]
                    )
                except (
                    NotImplementedError,
                    ResourceNotFoundError,
                    AttributeError,
                    TypeError,
                    ValueError,
                ):
                    continue
    return results


def exit_pytest_execution(
    message, return_code=SANITY_TESTS_FAILURE, filename=None, junitxml_property=None
):
    """Exit pytest execution

    Exit pytest execution; invokes pytest_sessionfinish.
    Optionally, log an error message to tests-collected-info/utilities/pytest_exit_errors/<filename>

    Args:
        message (str):  Message to display upon exit and to log in errors file
        return_code (int. Default: 99): Exit return code
        filename (str, optional. Default: None): filename where the given message will be saved
        junitxml_property (pytest plugin): record_testsuite_property
    """
    if filename:
        write_to_extras_file(
            extras_file_name=filename,
            content=message,
            extra_dir_name="pytest_exit_errors",
        )
    if junitxml_property:
        junitxml_property(name="exit_code", value=return_code)
    pytest.exit(msg=message, returncode=return_code)


def get_kubevirt_package_manifest(admin_client):
    """
    Gets kubevirt package manifest associated with hco-catalogsource label

    Args:
        admin_client (DynamicClient): dynamic client object

    Returns:
        Resource: Package manifest resource

    Raises:
        NotFoundError: when the kubevirt-hyperconverged package manifest associated with hco-catalogsource is not found
    """
    package_manifest_name = py_config["hco_cr_name"]
    label_selector = "catalog=hco-catalogsource"
    for resource_field in PackageManifest.get(
        dyn_client=admin_client,
        namespace=py_config["marketplace_namespace"],
        label_selector=label_selector,
        raw=True,
    ):
        if resource_field.metadata.name == package_manifest_name:
            LOGGER.info(
                f"Found expected packagemanefest: {resource_field.metadata.name}: "
                f"in catalog: {resource_field.metadata.labels.catalog}"
            )
            return resource_field
    raise NotFoundError(
        f"Not able to find any packagemanifest {package_manifest_name} in {label_selector} source."
    )


def get_subscription(admin_client, namespace, subscription_name):
    """
    Gets subscription by name

    Args:
        admin_client (DynamicClient): Dynamic client object
        namespace (str): Name of the namespace
        subscription_name (str): Name of the subscription

    Returns:
        Resource: subscription resource

    Raises:
        NotFoundError: when a given subscription is not found in a given namespace
    """
    for sub in Subscription.get(
        dyn_client=admin_client,
        name=subscription_name,
        namespace=namespace,
    ):
        return sub
    raise NotFoundError(
        f"Subscription {subscription_name} not found in namespace: {namespace}"
    )


def get_csv_by_name(csv_name, admin_client, namespace):
    """
    Gets csv from a given namespace by name

    Args:
        csv_name (str): Name of the csv
        admin_client (DynamicClient): dynamic client object
        namespace (str): namespace name

    Returns:
        Resource: csv resource

    Raises:
        NotFoundError: when a given csv is not found in a given namespace
    """
    for csv in ClusterServiceVersion.get(
        dyn_client=admin_client, namespace=namespace, name=csv_name
    ):
        return csv
    raise NotFoundError(f"Csv {csv_name} not found in namespace: {namespace}")


def get_clusterversion(dyn_client):
    for cvo in ClusterVersion.get(dyn_client=dyn_client):
        return cvo


def get_log_dir(path):
    for item in os.listdir(path):
        new_path = os.path.join(path, item)
        if os.path.isdir(new_path):
            return new_path
    raise FileNotFoundError(f"No log directory was created in '{path}'")
