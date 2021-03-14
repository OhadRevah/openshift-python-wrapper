import logging
import os
import re
import shutil
from configparser import ConfigParser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import bugzilla
import kubernetes
import requests
from colorlog import ColoredFormatter
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from ocp_resources.project import Project, ProjectRequest
from ocp_resources.resource import ResourceEditor
from ocp_resources.service import Service
from openshift.dynamic import DynamicClient
from pytest_testconfig import config as py_config

from utilities.constants import PODS_TO_COLLECT_INFO, TEST_COLLECT_INFO_DIR
from utilities.exceptions import CommandExecFailed


BUG_STATUS_CLOSED = ("VERIFIED", "ON_QA", "CLOSED")
BASE_IMAGES_DIR = "cnv-tests"
NON_EXIST_URL = "https://noneexist.com"
EXCLUDED_FROM_URL_VALIDATION = ("", NON_EXIST_URL)
INTERNAL_HTTP_SERVER_ADDRESS = "internal-http.kube-system"
LOGGER = logging.getLogger(__name__)


class Images:
    class Cirros:
        RAW_IMG = "cirros-0.4.0-x86_64-disk.raw"
        RAW_IMG_GZ = "cirros-0.4.0-x86_64-disk.raw.gz"
        RAW_IMG_XZ = "cirros-0.4.0-x86_64-disk.raw.xz"
        QCOW2_IMG = "cirros-0.4.0-x86_64-disk.qcow2"
        QCOW2_IMG_GZ = "cirros-0.4.0-x86_64-disk.qcow2.gz"
        QCOW2_IMG_XZ = "cirros-0.4.0-x86_64-disk.qcow2.xz"
        DISK_DEMO = "cirros-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/cirros-images"
        MOD_AUTH_BASIC_DIR = f"{BASE_IMAGES_DIR}/mod-auth-basic/cirros-images"
        DEFAULT_DV_SIZE = "3Gi"
        DEFAULT_MEMORY_SIZE = "64M"

    class Rhel:
        RHEL6_IMG = "rhel-610.qcow2"
        RHEL7_6_IMG = "rhel-76.qcow2"
        RHEL7_7_IMG = "rhel-77.qcow2"
        RHEL7_8_IMG = "rhel-78.qcow2"
        RHEL7_9_IMG = "rhel-79.qcow2"
        RHEL8_0_IMG = "rhel-8.qcow2"
        RHEL8_1_IMG = "rhel-81.qcow2"
        RHEL8_2_IMG = "rhel-82.qcow2"
        RHEL8_2_EFI_IMG = "rhel-82-efi.qcow2"
        RHEL8_3_IMG = "rhel-83.qcow2"
        RHEL8_4_IMG = "rhel-84.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/rhel-images"
        DEFAULT_DV_SIZE = "20Gi"

    class Windows:
        WIM10_IMG = "win_10.qcow2"
        WIM10_EFI_IMG = "win_10_efi.qcow2"
        WIN12_IMG = "win_12.qcow2"
        WIN16_IMG = "win_16.qcow2"
        WIN19_IMG = "win_19.qcow2"
        WIN19_RAW = "win19.raw"
        DIR = f"{BASE_IMAGES_DIR}/windows-images"
        RAW_DIR = f"{DIR}/raw_images"
        DEFAULT_DV_SIZE = "60Gi"

    class Fedora:
        FEDORA32_IMG = "Fedora-Cloud-Base-32-1.6.x86_64.qcow2"
        FEDORA33_IMG = "Fedora-Cloud-Base-33-1.2.x86_64.qcow2"
        DISK_DEMO = "fedora-cloud-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/fedora-images"
        DEFAULT_DV_SIZE = "10Gi"

    class CentOS:
        CENTOS7_IMG = "CentOS-7-x86_64-GenericCloud-2009.qcow2"
        CENTOS8_IMG = "CentOS-8-GenericCloud-8.2.2004-20200611.2.x86_64.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/centos-images"
        DEFAULT_DV_SIZE = "15Gi"

    class Cdi:
        QCOW2_IMG = "cirros-qcow2.img"
        DIR = f"{BASE_IMAGES_DIR}/cdi-test-images"


def label_project(name, label, admin_client):
    ns = Namespace(client=admin_client, name=name)
    ResourceEditor({ns: {"metadata": {"labels": label}}}).update()


def create_ns(name, client=None, kmp_vm_label=None, admin_client=None):
    """
    For kubemacpool opt_in, provide kmp_vm_label and admin_client as admin_client
    """
    if not client:
        with Namespace(name=name, label=kmp_vm_label) as ns:
            ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=120)
            yield ns
    else:
        with ProjectRequest(name=name, client=client):
            project = Project(name=name, client=client)
            project.wait_for_status(project.Status.ACTIVE, timeout=120)
            if kmp_vm_label:
                label_project(name=name, label=kmp_vm_label, admin_client=admin_client)
            yield project


def get_cert(server_type):
    path = os.path.join(
        "tests/storage/cdi_import", py_config[py_config["region"]][server_type]
    )
    with open(path, "r") as cert_content:
        data = cert_content.read()
    return data


class ClusterHosts:
    class Type:
        VIRTUAL = "virtual"
        PHYSICAL = "physical"


def get_bug_status(bugzilla_connection_params, bug):
    bzapi = bugzilla.Bugzilla(
        url=bugzilla_connection_params["bugzilla_url"],
        user=bugzilla_connection_params["bugzilla_username"],
        api_key=bugzilla_connection_params["bugzilla_api_key"],
    )
    return bzapi.getbug(objid=bug).status


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


def get_bugzilla_connection_params():
    bz_cfg = os.path.join(Path(".").resolve(), "bugzilla.cfg")
    parser = ConfigParser()
    # Open the file with the correct encoding
    parser.read(bz_cfg, encoding="utf-8")
    params_dict = {}
    for params in parser.items("DEFAULT"):
        params_dict[params[0]] = params[1]
    return params_dict


def get_pod_by_name_prefix(dyn_client, pod_prefix, namespace, get_all=False):
    """
    Args:
        pod_prefix: str or regex pattern
        get_all (bool): Return all pods if True else only the first one

    Returns:
        A list of all matching pods if get_all else only the first pod
    """
    pods = [
        pod
        for pod in Pod.get(dyn_client=dyn_client, namespace=namespace)
        if re.match(pod_prefix, pod.name)
    ]
    if pods:
        if get_all:
            return pods
        else:
            return pods[0]


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


def prepare_test_dir_log(item, prefix):
    if os.environ.get("CNV_TEST_COLLECT_LOGS", "0") != "0":
        test_cls_name = item.cls.__name__ if item.cls else ""
        test_dir_log = os.path.join(
            TEST_COLLECT_INFO_DIR,
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


def setup_logging(log_file="/tmp/pytest-tests.log"):
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
    basic_logger.setLevel(level=logging.INFO)

    log_handler.setFormatter(fmt=log_formatter)
    console_handler.setFormatter(fmt=log_formatter)

    logger_obj.addHandler(hdlr=console_handler)
    logger_obj.addHandler(hdlr=log_handler)
    logger_obj.setLevel(level=logging.INFO)

    logger_obj.propagate = False
    basic_logger.propagate = False


def separator(symbol_, val=None):
    terminal_width = shutil.get_terminal_size(fallback=(120, 40))[0]
    if not val:
        return f"{symbol_ * terminal_width}"

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"
