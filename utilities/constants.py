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


#  Network constants
SRIOV = "sriov"

#  Time constants
TIMEOUT_4MIN = 4 * 60
TIMEOUT_10MIN = 10 * 60
TIMEOUT_15MIN = 15 * 60
TIMEOUT_20MIN = 20 * 60
TIMEOUT_30MIN = 30 * 60
TIMEOUT_60MIN = 60 * 60
TIMEOUT_75MIN = 75 * 60
TIMEOUT_90MIN = 90 * 60
TIMEOUT_180MIN = 180 * 60

#  OS constants
OS_LOGIN_PARAMS = {
    "rhel": {
        "username": "cloud-user",
        "password": "redhat",
    },
    "fedora": {
        "username": "fedora",
        "password": "fedora",
    },
    "centos": {
        "username": "centos",
        "password": "centos",
    },
    "cirros": {
        "username": "cirros",
        "password": "gocubsgo",
    },
    "alpine": {
        "username": "root",
        "password": None,
    },
    "win": {
        "username": "Administrator",
        "password": "Heslo123",
    },
}

# IP stack families constants
IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"

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
