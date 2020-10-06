import os

import bugzilla
from pytest_testconfig import config as py_config
from resources.namespace import Namespace
from resources.project import Project, ProjectRequest
from resources.resource import ResourceEditor


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
        RHEL8_2_EFI_IMG = "rhel-82-efi.qcow2"
        RHEL8_3_IMG = "rhel-83.qcow2"
        RHEL8_4_IMG = "rhel-84.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/rhel-images"
        DEFAULT_DV_SIZE = "20Gi"

    class Windows:
        WIM10_IMG = "win_10.qcow2"
        WIN12_IMG = "win_12.qcow2"
        WIN16_IMG = "win_16.qcow2"
        WIN19_IMG = "win_19.qcow2"
        WIN19_RAW = "win19.raw"
        DIR = f"{BASE_IMAGES_DIR}/windows-images"
        RAW_DIR = f"{DIR}/raw_images"
        DEFAULT_DV_SIZE = "50Gi"

    class Fedora:
        FEDORA29_IMG = "Fedora-Cloud-Base-29-1.2.x86_64.qcow2"
        FEDORA30_IMG = "Fedora-Cloud-Base-30-1.2.x86_64.qcow2"
        FEDORA31_IMG = "Fedora-Cloud-Base-31-1.9.x86_64.qcow2"
        FEDORA32_IMG = "Fedora-Cloud-Base-32-1.6.x86_64.qcow2"
        DISK_DEMO = "fedora-cloud-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/fedora-images"
        DEFAULT_DV_SIZE = "10Gi"

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
    LARGER_PVC_REQUIRED = "A larger PVC is required"
    NOT_EXIST_IN_IMAGE_DIR = (
        "image file does not exist in image directory - directory is empty"
    )
    INVALID_FORMAT_FOR_QCOW = "Unable to process data: Invalid format qcow for image "
    COULD_NOT_OPEN_SIZE_TOO_BIG = "Unable to process data: qemu-img: Could not open '/data/disk.img': L1 size too big"
    REQUESTED_RANGE_NOT_SATISFIABLE = (
        "Unable to process data: qemu-img: curl: The requested URL returned error: "
        "416 Requested Range Not Satisfiable"
    )


def get_bug_status(bugzilla_connection_params, bug):
    bzapi = bugzilla.Bugzilla(
        url=bugzilla_connection_params["bugzilla_url"],
        user=bugzilla_connection_params["bugzilla_username"],
        api_key=bugzilla_connection_params["bugzilla_api_key"],
    )
    return bzapi.getbug(objid=bug).status
