import os
from configparser import ConfigParser
from pathlib import Path

import bugzilla
import kubernetes
import requests
from openshift.dynamic import DynamicClient
from pytest_testconfig import config as py_config
from resources.namespace import Namespace
from resources.pod import Pod
from resources.project import Project, ProjectRequest
from resources.resource import ResourceEditor


BUG_STATUS_CLOSED = ("VERIFIED", "ON_QA", "CLOSED")
BASE_IMAGES_DIR = "cnv-tests"
NON_EXIST_URL = "https://noneexist.com"
EXCLUDED_FROM_URL_VALIDATION = ("", NON_EXIST_URL)
INTERNAL_HTTP_SERVER_ADDRESS = "internal-http.kube-system"


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
    node_ips = {}
    for node in nodes:
        for addr in node.instance.status.addresses:
            if addr.type == "InternalIP":
                node_ips[node.name] = addr.address
    return node_ips


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
    pods = [
        pod
        for pod in Pod.get(dyn_client=dyn_client, namespace=namespace)
        if pod.name.startswith(pod_prefix)
    ]
    if pods:
        if get_all:
            return pods
        else:
            return pods[0]
