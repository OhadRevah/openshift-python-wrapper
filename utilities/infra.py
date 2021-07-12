import base64
import json
import logging
import os
import re
import shutil
from configparser import ConfigParser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import bugzilla
import kubernetes
import paramiko
import requests
from colorlog import ColoredFormatter
from jira import JIRA
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from ocp_resources.project import Project, ProjectRequest
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.service import Service
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config

from utilities.constants import PODS_TO_COLLECT_INFO, TIMEOUT_2MIN
from utilities.exceptions import CommandExecFailed


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
        list: A list of all matching pods if get_all (empty list if no pods found) else only the first pod.
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


def collect_logs_prepare_dirs():
    test_dir = os.environ.get("TEST_DIR_LOG")
    pods_dir = os.path.join(test_dir, "Pods")
    os.makedirs(test_dir, exist_ok=True)
    os.makedirs(pods_dir, exist_ok=True)
    return test_dir, pods_dir


def collect_logs_resources(resources_to_collect, namespace_name=None):
    get_kwargs = {"dyn_client": get_admin_client()}
    test_dir, _ = collect_logs_prepare_dirs()
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
    _, pods_dir = collect_logs_prepare_dirs()
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


def setup_logging(log_level, log_file="/tmp/pytest-tests.log"):
    logger_obj = logging.getLogger()
    basic_logger = logging.getLogger("basic")

    root_log_formatter = logging.Formatter(fmt="%(message)s")
    log_formatter = ColoredFormatter(
        fmt="%(name)s %(asctime)s %(log_color)s%(levelname) s%(reset)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={},
    )

    console_handler = logging.StreamHandler()
    log_handler = RotatingFileHandler(
        filename=log_file, maxBytes=100 * 1024 * 1024, backupCount=20
    )
    basic_console_handler = logging.StreamHandler()
    basic_log_handler = RotatingFileHandler(
        filename=log_file, maxBytes=100 * 1024 * 1024, backupCount=20
    )

    basic_log_handler.setFormatter(fmt=root_log_formatter)
    basic_console_handler.setFormatter(fmt=root_log_formatter)
    basic_logger.addHandler(hdlr=basic_log_handler)
    basic_logger.addHandler(hdlr=basic_console_handler)
    basic_logger.setLevel(level=log_level)

    log_handler.setFormatter(fmt=log_formatter)
    console_handler.setFormatter(fmt=log_formatter)

    logger_obj.addHandler(hdlr=console_handler)
    logger_obj.addHandler(hdlr=log_handler)
    logger_obj.setLevel(level=log_level)

    logger_obj.propagate = False
    basic_logger.propagate = False


def separator(symbol_, val=None):
    terminal_width = shutil.get_terminal_size(fallback=(120, 40))[0]
    if not val:
        return f"{symbol_ * terminal_width}"

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"


def generate_latest_os_dict(os_list):
    """
    Args:
        os_list (list): [rhel|windows|fedora]_os_matrix - a list of dicts

    Returns:
        tuple: (Latest OS name, latest supported OS dict) else raises an exception.
    """
    for os_dict in os_list:
        for os_version, os_values in os_dict.items():
            if os_values.get("latest"):
                return os_version, os_values
    assert False, f"No OS is marked as 'latest': {os_list}"


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


def get_bugzilla_connection_params():
    return get_connection_params(conf_file_name="bugzilla.cfg")


def get_bug_status(bugzilla_connection_params, bug):
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
    return os.environ.get("CNV_TEST_COLLECT_LOGS", "0") != "0"


def collect_resources_for_test(resources_to_collect, namespace_name=None):
    """
    This will collect all current resources matching the type(s) specified in the list of resources_to_collect

    A convenient function to explicitly collect certain resources
    simplified so it can be used from within a test case,
    probably you will want to use this during exception handling when a test fails
    ie: in order to collect resources that otherwise are not collected as part of the resource collection.

    will only actually collect resource if CNV_TEST_COLLECT_LOGS is set

    Args:
        resources_to_collect (list): list of Resource object classes to collect
        namespace_name (string): (optional) the namespace to use
    """
    if collect_logs():
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

    will only actually write to the file if CNV_TEST_COLLECT_LOGS is set

    Args:
        extras_file_name (string): name of the file to write
        content (string): the content of the file to write
        extra_dir_name (string): (optional) the directory name to create inside the test collect dir
    """
    if collect_logs():
        test_dir, _ = collect_logs_prepare_dirs()
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
