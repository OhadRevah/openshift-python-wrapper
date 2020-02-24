import logging
import os
import re
import socket
import ssl
import urllib.error
import urllib.request

import jinja2
import yaml
from pytest_testconfig import config as py_config
from resources.namespace import Namespace
from resources.project import Project, ProjectRequest


LOGGER = logging.getLogger(__name__)
BUG_STATUS_CLOSED = ("VERIFIED", "ON_QA", "CLOSED")
BASE_IMAGES_DIR = "cnv-tests"


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

    class Rhel:
        RHEL6_IMG = "rhel-610.qcow2"
        RHEL7_6_IMG = "rhel-76.qcow2"
        RHEL7_8_IMG = "rhel-78.qcow2"
        RHEL8_0_IMG = "rhel-8.qcow2"
        RHEL8_1_IMG = "rhel-81.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/rhel-images"

    class Windows:
        WIM10_IMG = "win_10.qcow2"
        WIN12_IMG = "win_12.qcow2"
        WIN16_IMG = "win_16.qcow2"
        WIN19_IMG = "win_19.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/windows-images"

    class Fedora:
        FEDORA29_IMG = "Fedora-Cloud-Base-29-1.2.x86_64.qcow2"
        FEDORA30_IMG = "Fedora-Cloud-Base-30-1.2.x86_64.qcow2"
        FEDORA31_IMG = "Fedora-Cloud-Base-31-1.9.x86_64.qcow2"
        DISK_DEMO = "fedora-cloud-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/fedora-images"

    class Cdi:
        QCOW2_IMG = "cirros-qcow2.img"
        DIR = f"{BASE_IMAGES_DIR}/cdi-test-images"


def get_images_external_http_server():
    """
    Fetch http_server url from config and return if available.
    """
    server = py_config[py_config["region"]]["http_server"]
    try:
        LOGGER.info(f"Testing connectivity to {server} HTTP server")
        assert urllib.request.urlopen(server, timeout=60).getcode() == 200
    except (urllib.error.URLError, socket.timeout) as e:
        LOGGER.error(
            f"URL Error when testing connectivity to {server} HTTP server.\nError: {e}"
        )
        raise

    return server


def get_images_https_server():
    """
    Fetch https_server url from config and return if available.
    """
    region = py_config["region"]
    server = py_config[region]["https_server"]

    myssl = ssl.create_default_context()
    myssl.check_hostname = False
    myssl.verify_mode = ssl.CERT_NONE
    try:
        assert urllib.request.urlopen(server, context=myssl).getcode() == 200
    except urllib.error.URLError:
        LOGGER.error("URL Error when testing connectivity to HTTPS server")
        raise
    return server


def create_ns(name, client=None):
    if not client:
        with Namespace(name=name) as ns:
            ns.wait_for_status(Namespace.Status.ACTIVE, timeout=120)
            yield ns
    else:
        with ProjectRequest(name=name, client=client):
            project = Project(name=name, client=client)
            project.wait_for_status(project.Status.ACTIVE, timeout=120)
            yield project


class MissingTemplateVariables(Exception):
    def __init__(self, var, template):
        self.var = var
        self.template = template

    def __str__(self):
        return f"Missing variables {self.var} for template {self.template}"


def generate_yaml_from_template(file_, **kwargs):
    """
    Generate JSON from yaml file_

    Args:
        file_ (str): Yaml file

    Keyword Args:
        name (str):
        image (str):

    Returns:
        dict: Generated from template file

    Raises:
        MissingTemplateVariables: If not all template variables exists

    Examples:
        generate_yaml_from_template(file_='path/to/file/name', name='vm-name-1')
    """
    with open(file_, "r") as stream:
        data = stream.read()

    # Find all template variables
    template_vars = [i.split()[1] for i in re.findall(r"{{ .* }}", data)]
    for var in template_vars:
        if var not in kwargs.keys():
            raise MissingTemplateVariables(var=var, template=file_)
    template = jinja2.Template(data)
    out = template.render(**kwargs)
    return yaml.safe_load(out)


def get_cert(server_type):
    path = os.path.join(
        "tests/storage/cdi_import", py_config[py_config["region"]][server_type]
    )
    with open(path, "r") as cert_content:
        data = cert_content.read()
    return data
