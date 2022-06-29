import ast
import base64
import http
import importlib
import io
import logging
import os
import platform
import re
import shlex
import stat
import subprocess
import tarfile
import zipfile
from configparser import ConfigParser
from contextlib import contextmanager
from pathlib import Path

import bugzilla
import kubernetes
import netaddr
import paramiko
import pytest
import requests
import urllib3
from jira import JIRA
from kubernetes.client import ApiException
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
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
    HCO_CATALOG_SOURCE,
    OPERATOR_NAME_SUFFIX,
    PODS_TO_COLLECT_INFO,
    SANITY_TESTS_FAILURE,
    TIMEOUT_2MIN,
    TIMEOUT_6MIN,
    TIMEOUT_10MIN,
    TIMEOUT_30MIN,
)
from utilities.exceptions import CommandExecFailed, UtilityPodNotFoundError


BUG_STATUS_CLOSED = ("VERIFIED", "ON_QA", "CLOSED", "RELEASE_PENDING")
JIRA_STATUS_CLOSED = ("closed", "done", "obsolete", "resolved")
NON_EXIST_URL = "https://noneexist.test"  # Use 'test' domain rfc6761
EXCLUDED_FROM_URL_VALIDATION = ("", NON_EXIST_URL)
INTERNAL_HTTP_SERVER_ADDRESS = "internal-http.kube-system"

DEFAULT_RESOURCE_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
VM_CRD = f"virtualmachines.{Resource.ApiGroup.KUBEVIRT_IO}"
ALL_CNV_CRDS = [
    f"cdiconfigs.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"cdis.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"dataimportcrons.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"datasources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"datavolumes.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"hostpathprovisioners.{Resource.ApiGroup.HOSTPATHPROVISIONER_KUBEVIRT_IO}",
    f"hyperconvergeds.{Resource.ApiGroup.HCO_KUBEVIRT_IO}",
    f"kubevirts.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"migrationpolicies.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"networkaddonsconfigs.{Resource.ApiGroup.NETWORKADDONSOPERATOR_NETWORK_KUBEVIRT_IO}",
    f"objecttransfers.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"ssps.{Resource.ApiGroup.SSP_KUBEVIRT_IO}",
    f"storageprofiles.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"tektontasks.{Resource.ApiGroup.TEKTONTASKS_KUBEVIRT_IO}",
    f"virtualmachineclusterflavors.{Resource.ApiGroup.FLAVOR_KUBEVIRT_IO}",
    f"virtualmachineflavors.{Resource.ApiGroup.FLAVOR_KUBEVIRT_IO}",
    f"virtualmachineinstancemigrations.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstancepresets.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstancereplicasets.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstances.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachinepools.{Resource.ApiGroup.POOL_KUBEVIRT_IO}",
    f"virtualmachinerestores.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    VM_CRD,
    f"virtualmachinesnapshotcontents.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    f"virtualmachinesnapshots.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
]


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


def create_ns(
    name,
    unprivileged_client=None,
    kmp_vm_label=None,
    admin_client=None,
    teardown=True,
    delete_timeout=TIMEOUT_6MIN,
):
    """
    For kubemacpool labeling opt-modes, provide kmp_vm_label and admin_client as admin_client
    """
    if not unprivileged_client:
        with Namespace(
            client=admin_client,
            name=name,
            label=kmp_vm_label,
            teardown=teardown,
            delete_timeout=delete_timeout,
        ) as ns:
            ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
            yield ns
    else:
        with ProjectRequest(name=name, client=unprivileged_client, teardown=teardown):
            project = Project(
                name=name,
                client=unprivileged_client,
                teardown=teardown,
                delete_timeout=delete_timeout,
            )
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
    raise ResourceNotFoundError(f"A pod with the {pod_prefix} prefix does not exist")


def run_ssh_commands(
    host, commands, get_pty=False, check_rc=True, timeout=TIMEOUT_30MIN
):
    """
    Run commands via SSH

    Args:
        host (Host): rrmngmnt host to execute the commands from.
        commands (list): List of multiple command lists [[cmd1, cmd2, cmd3]] or a list with a single command [cmd]
            Examples:
                 ["sudo", "reboot"], [["sleep", "5"], ["date"]]

        get_pty (bool): get_pty parameter for remote session (equivalent to -t argument for ssh)
        check_rc (bool): if True checks command return code and raises if rc != 0
        timeout (int): ssh exec timeout

    Returns:
        list: List of commands output.

    Raise:
        CommandExecFailed: If command failed to execute.
    """
    results = []
    commands = commands if isinstance(commands[0], list) else [commands]
    with host.executor().session() as ssh_session:
        for cmd in commands:
            rc, out, err = ssh_session.run_cmd(
                cmd=cmd, get_pty=get_pty, timeout=timeout
            )
            LOGGER.info(f"[SSH][{host.fqdn}] Executed: {' '.join(cmd)}")
            if rc and check_rc:
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


def get_bug(bug_id):
    bugzilla_connection_params = get_connection_params(conf_file_name="bugzilla.cfg")
    bzapi = bugzilla.Bugzilla(
        url=bugzilla_connection_params["bugzilla_url"],
        user=bugzilla_connection_params["bugzilla_username"],
        api_key=bugzilla_connection_params["bugzilla_api_key"],
    )
    return bzapi.getbug(objid=bug_id)


def get_jira_status(jira):
    jira_connection_params = get_connection_params(conf_file_name="jira.cfg")
    jira_connection = JIRA(
        token_auth=jira_connection_params["token"],
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
    Waits for all pods in a given namespace to reach Running/Completed state. To avoid catching all pods in running
    state too soon, use number_of_consecutive_checks with appropriate values.

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
                # Waits for all pods in a given namespace to be in final healthy state(running/completed).
                # We also need to keep track of pods marked for deletion as not running. This would ensure any pod that
                # was spinned up in place of pod marked for deletion, reaches healthy state before end of this check
                if pod.instance.metadata.get(
                    "deletionTimestamp"
                ) or pod.instance.status.phase not in (
                    pod.Status.RUNNING,
                    pod.Status.SUCCEEDED,
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
    daemon_set = DaemonSet(
        client=admin_client,
        namespace=namespace_name,
        name=daemonset_name,
    )
    if daemon_set.exists:
        return daemon_set
    raise ResourceNotFoundError(
        f"Daemonset: {daemonset_name} not found in namespace: {namespace_name}"
    )


def wait_for_consistent_resource_conditions(
    dynamic_client,
    expected_conditions,
    resource_kind,
    condition_key1,
    condition_key2,
    namespace=None,
    total_timeout=TIMEOUT_10MIN,
    polling_interval=5,
    consecutive_checks_count=10,
    exceptions_dict=None,
):
    """This function awaits certain conditions of a given resource_kind (HCO, CSV, etc.).

    Using TimeoutSampler loop and poll the CR (of the resource_kind type) and attempt to match the expected conditions
    against the actual conditions found in the CR.
    Since the conditions statuses might change, we use consecutive checks in order to have consistent results (stable),
    thereby ascertaining that the expected conditions are met over time.

    Args:
        dynamic_client (DynamicClient): admin client
        namespace (str, default: None): resource namespace. Not needed for cluster-scoped resources.
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
        exceptions_dict: TimeoutSampler exceptions_dict

    Raises:
        TimeoutExpiredError: raised when expected conditions are not met within the timeframe
    """
    samples = TimeoutSampler(
        wait_timeout=total_timeout,
        sleep=polling_interval,
        func=lambda: list(
            resource_kind.get(
                dyn_client=dynamic_client,
                namespace=namespace,
            )
        ),
        exceptions_dict=exceptions_dict,
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

    def exec(self, command, chroot_host=True, ignore_rc=False):
        _command = shlex.split(f"{'chroot /host' if chroot_host else ''} bash -c")
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
    hco_status_conditions,
    expected_hco_status,
    junitxml_property=None,
):
    if "cluster_health_check" in request.config.getoption("-m"):
        LOGGER.warning("Skipping cluster sanity test, got -m cluster_health_check")
        return

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
    skip_hco_status_condition_check = "--cluster-sanity-skip-hco-check"
    exceptions_filename = "cluster_sanity_failure.txt"
    try:
        if request.session.config.getoption(skip_cluster_sanity_check):
            LOGGER.warning(
                f"Skipping cluster sanity check, got {skip_cluster_sanity_check}"
            )
            return
        LOGGER.info(
            f"Running cluster sanity. (To skip cluster sanity check pass {skip_cluster_sanity_check} to pytest)"
        )
        # Check storage class only if --cluster-sanity-skip-storage-check not passed to pytest.
        if request.session.config.getoption(skip_storage_classes_check):
            LOGGER.warning(
                f"Skipping storage classes check, got {skip_storage_classes_check}"
            )
        else:
            LOGGER.info(
                f"Check storage classes sanity. (To skip storage class sanity check pass {skip_storage_classes_check} "
                f"to pytest)"
            )
            _storage_sanity_check()

        # Check nodes only if --cluster-sanity-skip-nodes-check not passed to pytest.
        if request.session.config.getoption(skip_nodes_check):
            LOGGER.warning(f"Skipping nodes check, got {skip_nodes_check}")

        else:
            # validate that all the nodes are ready and schedulable and CNV pods are running
            LOGGER.info(
                f"Check nodes sanity. (To skip nodes sanity check pass {skip_nodes_check} to pytest)"
            )
            validate_nodes_ready(nodes=nodes)
            validate_nodes_schedulable(nodes=nodes)
            wait_for_pods_running(admin_client=admin_client, namespace=hco_namespace)

        # Check hco.status.conditions only if --cluster-sanity-skip-hco-check not passed to pytest.
        if request.session.config.getoption(skip_hco_status_condition_check):
            LOGGER.warning(
                f"Skipping HCO status conditions check, got {skip_hco_status_condition_check}"
            )
        else:
            # validate that hco.status.conditions indicates it is healthy
            validate_hco_status_conditions(
                hco_status_conditions=hco_status_conditions,
                expected_hco_status=expected_hco_status,
            )
    except ClusterSanityError as ex:
        exit_pytest_execution(
            filename=exceptions_filename,
            message=ex.err_str,
            junitxml_property=junitxml_property,
        )


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
        "__pycache__",
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
    exclude_resources_prefix = (
        "deployer-",
        "default-",
        "builder-",
        "olm-operator-heap",
        "catalog-operator-heap",
        "collect-profiles",
    )
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
    return get_raw_package_manifest(
        admin_client=admin_client,
        name=py_config["hco_cr_name"],
        catalog_source=HCO_CATALOG_SOURCE,
    )


def get_raw_package_manifest(admin_client, name, catalog_source):
    """
    Gets PackageManifest ResourceField associated with catalog source.
    Multiple PackageManifest Resources exist with the same name but different labels.
    Requires raw=True

    Args:
        admin_client (DynamicClient): dynamic client object
        name (str): Name of PackageManifest
        catalog_source (str): Catalog source

    Returns:
        ResourceField or None: PackageManifest ResourceField or None if no matching resource found
    """
    for resource_field in PackageManifest.get(
        dyn_client=admin_client,
        namespace=py_config["marketplace_namespace"],
        field_selector=f"metadata.name={name}",
        label_selector=f"catalog={catalog_source}",
        raw=True,  # multiple packagemanifest exists with the same name but different labels
    ):
        LOGGER.info(
            f"Found expected packagemanefest: {resource_field.metadata.name}: "
            f"in catalog: {resource_field.metadata.labels.catalog}"
        )
        return resource_field
    LOGGER.warning(
        f"Not able to find any packagemanifest {name} in {catalog_source} source."
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
    subscription = Subscription(
        client=admin_client,
        name=subscription_name,
        namespace=namespace,
    )
    if subscription.exists:
        return subscription
    raise ResourceNotFoundError(
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
    csv = ClusterServiceVersion(client=admin_client, namespace=namespace, name=csv_name)
    if csv.exists:
        return csv
    raise ResourceNotFoundError(f"Csv {csv_name} not found in namespace: {namespace}")


def get_clusterversion(dyn_client):
    for cvo in ClusterVersion.get(dyn_client=dyn_client):
        return cvo


def get_log_dir(path):
    for item in os.listdir(path):
        new_path = os.path.join(path, item)
        if os.path.isdir(new_path):
            return new_path
    raise FileNotFoundError(f"No log directory was created in '{path}'")


def get_deployments(admin_client, namespace):
    return list(Deployment.get(dyn_client=admin_client, namespace=namespace))


def cnv_target_images(target_related_images_name_and_versions):
    return [item["image"] for item in target_related_images_name_and_versions.values()]


def get_related_images_name_and_version(dyn_client, hco_namespace, version):
    related_images_name_and_versions = {}
    csv = get_csv_by_name(
        admin_client=dyn_client,
        namespace=hco_namespace,
        csv_name=version,
    )
    for item in csv.instance.spec.relatedImages:
        # Example: 'registry.redhat.io/container-native-virtualization/node-maintenance-operator:v2.6.3-1'
        image_name_version = re.search(
            r".*/(?P<name>.*?):(?P<version>.*)", item["name"]
        ).groupdict()
        image_name = image_name_version["name"]
        related_images_name_and_versions[image_name] = {
            "image": item["image"],
            "version": image_name_version["version"],
            "is_operator_image": image_name.endswith(OPERATOR_NAME_SUFFIX),
        }
    return related_images_name_and_versions


def is_bug_open(bug_id):
    bug = get_bug(bug_id=bug_id)
    bug_status = bug.status
    status_for_logger = f"Bug {bug_id}: {bug.summary} status is {bug_status}"
    if bug_status not in BUG_STATUS_CLOSED:
        LOGGER.info(status_for_logger)
        return True

    LOGGER.warning(f"{status_for_logger} bug should be removed from the codebase")
    return False


def run_command(command, verify_stderr=True, shell=False):
    """
    Run command locally.

    Args:
        command (list): Command to run
        verify_stderr (bool, default True): Check command stderr
        shell (bool, default False): run subprocess with shell toggle

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    sub_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
    )
    out, err = sub_process.communicate()
    out_decoded = out.decode("utf-8")
    err_decoded = err.decode("utf-8")

    error_msg = f"Failed to run {command}. rc: {sub_process.returncode}, out: {out_decoded}, error: {err_decoded}"
    if sub_process.returncode != 0:
        LOGGER.error(error_msg)
        return False, out_decoded, err_decoded

    # From this point and onwards we are guaranteed that sub_process.returncode == 0
    if err_decoded and verify_stderr:
        LOGGER.error(error_msg)
        return False, out_decoded, err_decoded

    return True, out_decoded, err_decoded


def run_cnv_must_gather(must_gather_cmd):
    LOGGER.info(f"Running: {must_gather_cmd}")
    return run_command(command=shlex.split(must_gather_cmd))[1]


def create_must_gather_command(dest_dir, image_url, script_name=None):
    base_command = f"oc adm must-gather --image={image_url} --dest-dir={dest_dir}"
    return f"{base_command} -- {script_name}" if script_name else base_command


def run_virtctl_command(command, namespace=None):
    """
    Run virtctl command

    Args:
        command (list): Command to run
        namespace (str, default:None): Namespace to send to virtctl command

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    virtctl_cmd = ["virtctl"]
    kubeconfig = os.getenv("KUBECONFIG")
    if namespace:
        virtctl_cmd.extend(["-n", namespace])

    if kubeconfig:
        virtctl_cmd.extend(["--kubeconfig", kubeconfig])

    virtctl_cmd.extend(command)
    res, out, err = run_command(command=virtctl_cmd)

    return res, out, err


def validate_hco_status_conditions(hco_status_conditions, expected_hco_status):
    current_status = {
        condition["type"]: condition["status"] for condition in hco_status_conditions
    }
    mismatch_statuses = []

    for condition_type, condition_status in expected_hco_status.items():
        if current_status[condition_type] != condition_status:
            mismatch_statuses.append(
                f"Current condition type {condition_type} does not match expected status {condition_status}"
            )

    if mismatch_statuses:
        mismatch_str = "\n".join(mismatch_statuses)
        raise ClusterSanityError(
            err_str=f"{mismatch_str} \nHCO is unhealthy. "
            f"Expected {expected_hco_status}, Current: {hco_status_conditions}"
        )


def is_jira_open(jira_id):
    return get_jira_status(jira=jira_id) not in JIRA_STATUS_CLOSED


def get_hyperconverged_resource(client, hco_ns_name):
    hco_name = py_config["hco_cr_name"]
    hco = HyperConverged(
        client=client,
        namespace=hco_ns_name,
        name=hco_name,
    )
    if hco.exists:
        return hco
    raise ResourceNotFoundError(
        f"Hyperconverged: {hco_name} not found in {hco_ns_name}"
    )


def get_utility_pods_from_nodes(nodes, admin_client, label_selector):
    pods = list(Pod.get(admin_client, label_selector=label_selector))
    nodes_without_utility_pods = [
        node.name for node in nodes if node.name not in [pod.node.name for pod in pods]
    ]
    assert (
        not nodes_without_utility_pods
    ), f"Missing pods with label {label_selector} for: {' '.join(nodes_without_utility_pods)}"
    return [pod for pod in pods if pod.node.name in [node.name for node in nodes]]


def label_nodes(nodes, labels):
    updates = [
        ResourceEditor({node: {"metadata": {"labels": labels}}}) for node in nodes
    ]

    for update in updates:
        update.update(backup_resources=True)
    yield nodes
    for update in updates:
        update.restore()


def get_daemonsets(admin_client, namespace):
    return list(DaemonSet.get(dyn_client=admin_client, namespace=namespace))


@contextmanager
def scale_deployment_replicas(deployment_name, namespace, replica_count):
    """
    It scales deployments replicas. At the end of the test restores them back
    """
    deployment = Deployment(name=deployment_name, namespace=namespace)
    initial_replicas = deployment.instance.spec.replicas
    deployment.scale_replicas(replica_count=replica_count)
    deployment.wait_for_replicas(deployed=bool(replica_count > 0))
    yield
    deployment.scale_replicas(replica_count=initial_replicas)
    deployment.wait_for_replicas(deployed=bool(initial_replicas > 0))


def get_kube_system_namespace():
    ns = Namespace(name="kube-system")
    if ns.exists:
        return ns
    raise ResourceNotFoundError(f"{ns.name} namespace not found")


def get_console_spec_links(admin_client, name):
    console_cli_download_resource_content = ConsoleCLIDownload(
        name=name, client=admin_client
    )
    if console_cli_download_resource_content.exists:
        return console_cli_download_resource_content.instance.spec.links

    raise ResourceNotFoundError(f"{name} ConsoleCLIDownload not found")


def get_all_console_links(console_cli_downloads_spec_links):
    all_urls = [entry["href"] for entry in console_cli_downloads_spec_links]
    assert all_urls, (
        "No URL entries found in the resource: "
        f"console_cli_download_resource_content={console_cli_downloads_spec_links}"
    )
    return all_urls


def download_and_extract_file_from_cluster(tmpdir, url):
    """
    Download and extract archive file from the cluster

    Args:
        tmpdir (py.path.local): temporary folder to download the files.
        url (str): URL to download from.

    Returns:
        list: list of extracted filenames
    """
    zip_file_extension = ".zip"
    LOGGER.info(f"Downloading virtctl archive: url={url}")
    urllib3.disable_warnings()  # TODO: remove this when we fix the SSL warning
    response = requests.get(url, verify=False)
    assert (
        response.status_code == http.HTTPStatus.OK
    ), f"Response status code: {response.status_code}"
    archive_file_data = io.BytesIO(initial_bytes=response.content)
    LOGGER.info("Extract the archive")
    if url.endswith(zip_file_extension):
        archive_file_object = zipfile.ZipFile(file=archive_file_data)
    else:
        archive_file_object = tarfile.open(fileobj=archive_file_data, mode="r")
    archive_file_object.extractall(path=tmpdir)
    extracted_filenames = (
        archive_file_object.namelist()
        if url.endswith(zip_file_extension)
        else archive_file_object.getnames()
    )
    return [os.path.join(tmpdir.strpath, namelist) for namelist in extracted_filenames]


def get_and_extract_file_from_cluster(urls, system_os, dest_dir):
    for url in urls:
        if system_os in url:
            extracted_files = download_and_extract_file_from_cluster(
                tmpdir=dest_dir, url=url
            )
            assert (
                len(extracted_files) == 1
            ), f"Only a single file expected in archive: extracted_files={extracted_files}"
            return extracted_files[0]

    raise UrlNotFoundError(f"virtctl url not found for system_os={system_os}")


def download_file_from_cluster(get_console_spec_links_name, dest_dir):
    console_cli_links = get_console_spec_links(
        admin_client=get_admin_client(),
        name=get_console_spec_links_name,
    )
    virtctl_urls = get_all_console_links(
        console_cli_downloads_spec_links=console_cli_links
    )
    virtctl_binary_file = get_and_extract_file_from_cluster(
        system_os=platform.system().lower(),
        urls=virtctl_urls,
        dest_dir=dest_dir,
    )
    os.chmod(virtctl_binary_file, stat.S_IRUSR | stat.S_IXUSR)
