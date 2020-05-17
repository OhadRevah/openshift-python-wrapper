import os

from pytest_testconfig import config as py_config
from resources.cluster_service_version import ClusterServiceVersion
from resources.namespace import Namespace
from resources.project import Project, ProjectRequest


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
        RHEL7_7_IMG = "rhel-77.qcow2"
        RHEL7_8_IMG = "rhel-78.qcow2"
        RHEL7_9_IMG = "rhel-79.qcow2"
        RHEL8_0_IMG = "rhel-8.qcow2"
        RHEL8_1_IMG = "rhel-81.qcow2"
        RHEL8_2_IMG = "rhel-82.qcow2"
        RHEL8_3_IMG = "rhel-83.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/rhel-images"

    class Windows:
        WIM10_IMG = "win_10.qcow2"
        WIN12_IMG = "win_12.qcow2"
        WIN16_IMG = "win_16.qcow2"
        WIN19_IMG = "win_19.qcow2"
        WIN19_RAW = "win19.raw"
        DIR = f"{BASE_IMAGES_DIR}/windows-images"
        RAW_DIR = f"{DIR}/raw_images"

    class Fedora:
        FEDORA29_IMG = "Fedora-Cloud-Base-29-1.2.x86_64.qcow2"
        FEDORA30_IMG = "Fedora-Cloud-Base-30-1.2.x86_64.qcow2"
        FEDORA31_IMG = "Fedora-Cloud-Base-31-1.9.x86_64.qcow2"
        FEDORA32_IMG = "Fedora-Cloud-Base-32-1.6.x86_64.qcow2"
        DISK_DEMO = "fedora-cloud-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/fedora-images"

    class Cdi:
        QCOW2_IMG = "cirros-qcow2.img"
        DIR = f"{BASE_IMAGES_DIR}/cdi-test-images"


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


class ErrorMsg:
    """
    error messages that might show in pod containers
    """

    EXIT_STATUS_1 = "Unable to process data: exit status 1"
    EXIT_STATUS_2 = "Unable to process data: exit status 2"
    UNABLE_TO_CONNECT_TO_HTTP = "Unable to connect to http data source"
    CERTIFICATE_SIGNED_UNKNOWN_AUTHORITY = "certificate signed by unknown authority"
    DISK_IMAGE_IN_CONTAINER_NOT_FOUND = (
        "Unable to process data: Failed to find VM disk image file in the container "
        "image"
    )
    SHRINK_NOT_SUPPORTED = "shrink not yet supported"


def get_current_cnv_version(dyn_client, hco_namespace):
    for csv in ClusterServiceVersion.get(
        dyn_client=dyn_client, namespace=hco_namespace
    ):
        return csv.instance.spec.version
