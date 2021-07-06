import os

from ocp_resources.datavolume import DataVolume
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.node_network_configuration_policy import (
    NodeNetworkConfigurationPolicy,
)
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.service import Service
from ocp_resources.virtual_machine import (
    VirtualMachine,
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
)


# Images
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
        RHEL8_5_IMG = "rhel-85.qcow2"
        RHEL9_0_IMG = "rhel-90.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/rhel-images"
        DEFAULT_DV_SIZE = "20Gi"

    class Windows:
        WIM10_IMG = "win_10.qcow2"
        WIM10_WSL2_IMG = "win_10_wsl2.qcow2"
        WIM10_EFI_IMG = "win_10_efi.qcow2"
        WIM10_NVIDIA_IMG = "win_10_nv.qcow2"
        WIN12_IMG = "win_12.qcow2"
        WIN16_IMG = "win_16.qcow2"
        WIN19_IMG = "win_19.qcow2"
        WIN19_NVIDIA_IMG = "win_19_nv.qcow2"
        WIN19_RAW = "win19.raw"
        DIR = f"{BASE_IMAGES_DIR}/windows-images"
        RAW_DIR = f"{DIR}/raw_images"
        DEFAULT_DV_SIZE = "60Gi"
        NVIDIA_DV_SIZE = "70Gi"
        WSL2_DV_SIZE = "40Gi"
        DEFAULT_MEMORY_SIZE = "8Gi"
        DEFAULT_CPU_THREADS = 2

    class Fedora:
        FEDORA32_IMG = "Fedora-Cloud-Base-32-1.6.x86_64.qcow2"
        FEDORA33_IMG = "Fedora-Cloud-Base-33-1.2.x86_64.qcow2"
        FEDORA34_IMG = "Fedora-Cloud-Base-34-1.2.x86_64.qcow2"
        DISK_DEMO = "fedora-cloud-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/fedora-images"
        DEFAULT_DV_SIZE = "10Gi"

    class CentOS:
        CENTOS7_IMG = "CentOS-7-x86_64-GenericCloud-2009.qcow2"
        CENTOS8_IMG = "CentOS-8-GenericCloud-8.3.2011-20201204.2.x86_64.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/centos-images"
        DEFAULT_DV_SIZE = "15Gi"

    class Cdi:
        QCOW2_IMG = "cirros-qcow2.img"
        DIR = f"{BASE_IMAGES_DIR}/cdi-test-images"


#  Network constants
SRIOV = "sriov"
IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"

#  Time constants
TIMEOUT_20SEC = 20
TIMEOUT_30SEC = 30
TIMEOUT_90SEC = 90
TIMEOUT_1MIN = 60
TIMEOUT_2MIN = 2 * 60
TIMEOUT_3MIN = 3 * 60
TIMEOUT_4MIN = 4 * 60
TIMEOUT_5MIN = 5 * 60
TIMEOUT_6MIN = 6 * 60
TIMEOUT_8MIN = 8 * 60
TIMEOUT_10MIN = 10 * 60
TIMEOUT_12MIN = 12 * 60
TIMEOUT_15MIN = 15 * 60
TIMEOUT_20MIN = 20 * 60
TIMEOUT_25MIN = 25 * 60
TIMEOUT_30MIN = 30 * 60
TIMEOUT_35MIN = 35 * 60
TIMEOUT_40MIN = 40 * 60
TIMEOUT_60MIN = 60 * 60
TIMEOUT_75MIN = 75 * 60
TIMEOUT_90MIN = 90 * 60
TIMEOUT_180MIN = 180 * 60

#  OS constants
OS_FLAVOR_CIRROS = "cirros"
OS_FLAVOR_WINDOWS = "win"
OS_FLAVOR_RHEL = "rhel"
OS_FLAVOR_FEDORA = "fedora"
OS_FLAVOR_CENTOS = "centos"

OS_LOGIN_PASSWORD = "password"
OS_LOGIN_PARAMS = {
    OS_FLAVOR_RHEL: {
        "username": "cloud-user",
        "password": OS_LOGIN_PASSWORD,
    },
    OS_FLAVOR_FEDORA: {
        "username": "fedora",
        "password": OS_LOGIN_PASSWORD,
    },
    OS_FLAVOR_CENTOS: {
        "username": "centos",
        "password": OS_LOGIN_PASSWORD,
    },
    OS_FLAVOR_CIRROS: {
        "username": "cirros",
        "password": "gocubsgo",
    },
    OS_FLAVOR_WINDOWS: {
        "username": "Administrator",
        "password": "Heslo123",
    },
}

# Collect logs constants
TEST_LOG_FILE = "pytest-tests.log"
TEST_COLLECT_INFO_DIR = "tests-collected-info"
RESOURCES_TO_COLLECT_INFO = [
    DataVolume,
    PersistentVolume,
    PersistentVolumeClaim,
    VirtualMachine,
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
    NetworkAttachmentDefinition,
    NodeNetworkConfigurationPolicy,
    NodeNetworkState,
    Service,
]
PODS_TO_COLLECT_INFO = [
    "virt-launcher",
    "virt-api",
    "virt-controller",
    "virt-handler",
    "virt-template-validator",
    "cdi-importer",
]

# GPU constants
# The GPU tests require GPU Device on the Worker Nodes.
# ~]$ lspci -nnv | grep -i NVIDIA  , should display the GPU_DEVICE_ID
GPU_DEVICE_NAME = "nvidia.com/TU104GL_Tesla_T4"
GPU_DEVICE_ID = "10de:1eb8"

# cloud-init constants
CLOUD_INIT_DISK_NAME = "cloudinitdisk"
CLOUND_INIT_CONFIG_DRIVE = "cloudInitConfigDrive"
CLOUD_INIT_NO_CLOUD = "cloudInitNoCloud"

# Kubemacpool constants
KMP_VM_ASSIGNMENT_LABEL = "mutatevirtualmachines.kubemacpool.io"
KMP_ENABLED_LABEL = "allocate"

# SSH constants
CNV_SSH_KEY_PATH = os.path.join(os.getcwd(), "utilities/cnv-qe-jenkins.key")

# CPU ARCH
INTEL = "Intel"
AMD = "AMD"

# unprivileged_client constants
UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"
