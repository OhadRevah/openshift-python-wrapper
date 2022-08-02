import os

from ocp_resources.cdi import CDI
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import Resource
from ocp_resources.ssp import SSP


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
        DEFAULT_DV_SIZE = "1Gi"
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
        RHEL8_6_IMG = "rhel-86.qcow2"
        RHEL9_0_IMG = "rhel-90.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/rhel-images"
        DEFAULT_DV_SIZE = "20Gi"
        DEFAULT_MEMORY_SIZE = "1.5Gi"

    class Windows:
        WIM10_IMG = "win_10.qcow2"
        WIM10_WSL2_IMG = "win_10_wsl2.qcow2"
        WIM10_EFI_IMG = "win_10_efi.qcow2"
        WIM10_NVIDIA_IMG = "win_10_nv.qcow2"
        WIN12_IMG = "win_12.qcow2"
        WIN16_IMG = "win_16.qcow2"
        WIN19_IMG = "win_19.qcow2"
        WIN11_IMG = "win_11.qcow2"
        WIN19_NVIDIA_IMG = "win_19_nv.qcow2"
        WIN19_RAW = "win19.raw"
        DIR = f"{BASE_IMAGES_DIR}/windows-images"
        RAW_DIR = f"{DIR}/raw_images"
        DEFAULT_DV_SIZE = "70Gi"
        NVIDIA_DV_SIZE = "75Gi"
        WSL2_DV_SIZE = "40Gi"
        DEFAULT_MEMORY_SIZE = "8Gi"
        DEFAULT_CPU_THREADS = 2

    class Fedora:
        FEDORA35_IMG = "Fedora-Cloud-Base-35-1.2.x86_64.qcow2"
        DISK_DEMO = "fedora-cloud-registry-disk-demo"
        DIR = f"{BASE_IMAGES_DIR}/fedora-images"
        DEFAULT_DV_SIZE = "10Gi"

    class CentOS:
        CENTOS7_IMG = "CentOS-7-x86_64-GenericCloud-2009.qcow2"
        CENTOS_STREAM_8_IMG = "CentOS-Stream-GenericCloud-8-20210603.0.x86_64.qcow2"
        CENTOS_STREAM_9_IMG = "CentOS-Stream-GenericCloud-9-20220107.0.x86_64.qcow2"
        DIR = f"{BASE_IMAGES_DIR}/centos-images"
        DEFAULT_DV_SIZE = "15Gi"

    class Cdi:
        QCOW2_IMG = "cirros-qcow2.img"
        DIR = f"{BASE_IMAGES_DIR}/cdi-test-images"


# Virtctl constants
VIRTCTL_CLI_DOWNLOADS = "virtctl-clidownloads-kubevirt-hyperconverged"

#  Network constants
SRIOV = "sriov"
IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"
MTU_9000 = 9000
IPV4_STR = "ipv4"
IPV6_STR = "ipv6"
CLUSTER_NETWORK_ADDONS_OPERATOR = "cluster-network-addons-operator"
BRIDGE_MARKER = "bridge-marker"
KUBE_CNI_LINUX_BRIDGE_PLUGIN = "kube-cni-linux-bridge-plugin"
LINUX_BRIDGE = "linux-bridge"
OVS_BRIDGE = "ovs-bridge"
KUBEMACPOOL_CERT_MANAGER = "kubemacpool-cert-manager"
KUBEMACPOOL_MAC_CONTROLLER_MANAGER = "kubemacpool-mac-controller-manager"
KUBEMACPOOL_MAC_RANGE_CONFIG = "kubemacpool-mac-range-config"
NMSTATE_HANDLER = "nmstate-handler"
ISTIO_SYSTEM_DEFAULT_NS = "istio-system"
SSH_PORT_22 = 22
ACTIVE_BACKUP = "active-backup"

#  Time constants
TIMEOUT_5SEC = 5
TIMEOUT_10SEC = 10
TIMEOUT_15SEC = 15
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
TIMEOUT_9MIN = 9 * 60
TIMEOUT_10MIN = 10 * 60
TIMEOUT_11MIN = 11 * 60
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
TIMEOUT_12HRS = 12 * 60 * 60

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


# OpenShift Virtualization components constants
VIRT_OPERATOR = "virt-operator"
VIRT_LAUNCHER = "virt-launcher"
VIRT_API = "virt-api"
VIRT_CONTROLLER = "virt-controller"
VIRT_HANDLER = "virt-handler"
VIRT_TEMPLATE_VALIDATOR = "virt-template-validator"
SSP_KUBEVIRT_HYPERCONVERGED = "ssp-kubevirt-hyperconverged"
SSP_OPERATOR = "ssp-operator"
CDI_OPERATOR = "cdi-operator"
CDI_APISERVER = "cdi-apiserver"
CDI_DEPLOYMENT = "cdi-deployment"
CDI_UPLOADPROXY = "cdi-uploadproxy"
HCO_OPERATOR = "hco-operator"
HCO_WEBHOOK = "hco-webhook"
HOSTPATH_CSI_BASIC = "hostpath-csi-basic"
HOSTPATH_PROVISIONER_CSI = "hostpath-provisioner-csi"
HOSTPATH_PROVISIONER = "hostpath-provisioner"
HOSTPATH_PROVISIONER_OPERATOR = "hostpath-provisioner-operator"
HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD = "hyperconverged-cluster-cli-download"
KUBEVIRT_HCO_NAME = "kubevirt-kubevirt-hyperconverged"
HCO_PART_OF_LABEL_VALUE = "hyperconverged-cluster"
MANAGED_BY_LABEL_VALUE_OLM = "olm"
HPP_POOL = "hpp-pool"
HCO_CATALOG_SOURCE = "hco-catalogsource"
TEKTON_TASK_OPERATOR = "tekton-tasks-operator"
KUBEVIRT_PLUGIN = "kubevirt-plugin"

# Namespace constants
OPENSHIFT_NAMESPACE = "openshift"
DEFAULT_NAMESPACE = "default"

# CDI related constants
CDI_SECRETS = [
    "cdi-apiserver-server-cert",
    "cdi-apiserver-signer",
    "cdi-uploadproxy-server-cert",
    "cdi-uploadproxy-signer",
    "cdi-uploadserver-client-cert",
    "cdi-uploadserver-client-signer",
    "cdi-uploadserver-signer",
]

# Miscellaneous constants
UTILITY = "utility"
OPERATOR_NAME_SUFFIX = "operator"
PODS_TO_COLLECT_INFO = [
    HCO_OPERATOR,
    VIRT_OPERATOR,
    SSP_OPERATOR,
    VIRT_LAUNCHER,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_TEMPLATE_VALIDATOR,
    "cdi-importer",
    UTILITY,
    NMSTATE_HANDLER,
]


# GPU/vGPU Common constants
# The GPU tests require GPU Device on the Worker Nodes.
# ~]$ lspci -nnv | grep -i NVIDIA  , should display the GPU_DEVICE_ID
GPU_DEVICE_MANUFACTURER = "nvidia.com"
GPU_DEVICE_ID = "10de:1eb8"

# GPU Passthrough constants
GPU_DEVICE_NAME = f"{GPU_DEVICE_MANUFACTURER}/TU104GL_Tesla_T4"

# vGPU constants
VGPU_DEVICE_NAME = f"{GPU_DEVICE_MANUFACTURER}/GRID_T4_2Q"
MDEV_NAME = "GRID T4-2Q"
MDEV_AVAILABLE_INSTANCES = "8"
MDEV_TYPE = "nvidia-231"
NVIDIA_GRID_DRIVER_NAME = "NVIDIA GRID"

VGPU_GRID_T4_16Q_NAME = f"{GPU_DEVICE_MANUFACTURER}/GRID_T4_16Q"
MDEV_GRID_T4_16Q_NAME = "GRID T4-16Q"
MDEV_GRID_T4_16Q_AVAILABLE_INSTANCES = "1"
MDEV_GRID_T4_16Q_TYPE = "nvidia-234"

# Kernel Device Driver
# Compute: GPU Devices are bound to this Kernel Driver for GPU Passthrough.
# Networking: For SRIOV Node Policy, The driver type for the virtual functions
KERNEL_DRIVER = "vfio-pci"


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

# Red Hat Subscription Manager credentials.
RHSM_USER = "cnv-qe-automation-stage"
RHSM_PASSWD = "redhatredhat"

# KUBECONFIG variables
KUBECONFIG = "KUBECONFIG"

# commands
LS_COMMAND = "ls -1 | sort | tr '\n' ' '"

# hotplug disk serial
HOTPLUG_DISK_SERIAL = "1234567890"

# pyetest configuration
SANITY_TESTS_FAILURE = 99
HCO_SUBSCRIPTION = "hco-operatorhub"

# VM configuration
LIVE_MIGRATE = "LiveMigrate"
ROOTDISK = "rootdisk"

# W/A for BZ 2026621
# TODO: Remove after BZ 2026621 fixed
WORKERS_TYPE = "WORKERS_TYPE"

# Upgrade tests configuration
DEPENDENCY_SCOPE_SESSION = "session"

# Feature gates
ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE = "enableCommonBootImageImport"

# Common templates constants
DATA_SOURCE_NAME = "DATA_SOURCE_NAME"
DATA_SOURCE_NAMESPACE = "DATA_SOURCE_NAMESPACE"
SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME = "dataImportCronTemplates"
COMMON_TEMPLATES_KEY_NAME = "commonTemplates"

ALL_CNV_PODS = [
    BRIDGE_MARKER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER_CSI,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEVIRT_PLUGIN,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    TEKTON_TASK_OPERATOR,
]
ALL_CNV_DEPLOYMENTS = [
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER_OPERATOR,
    HPP_POOL,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEVIRT_PLUGIN,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    TEKTON_TASK_OPERATOR,
]
ALL_CNV_DAEMONSETS = [
    BRIDGE_MARKER,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    HOSTPATH_PROVISIONER_CSI,
    VIRT_HANDLER,
]
# Node labels
NODE_TYPE_WORKER_LABEL = {"node-type": "worker"}
NODE_ROLE_KUBERNETES_IO = "node-role.kubernetes.io"
WORKER_NODE_LABEL_KEY = f"{NODE_ROLE_KUBERNETES_IO}/worker"
MASTER_NODE_LABEL_KEY = f"{NODE_ROLE_KUBERNETES_IO}/master"
CDI_KUBEVIRT_HYPERCONVERGED = "cdi-kubevirt-hyperconverged"
TSC_FREQUENCY = "tsc-frequency"

# Container constants
CNV_TESTS_CONTAINER = "CNV_TESTS_CONTAINER"
DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
DEFAULT_KUBEVIRT_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.CREATED: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
DEFAULT_RESOURCE_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
EXPECTED_STATUS_CONDITIONS = {
    HyperConverged: DEFAULT_HCO_CONDITIONS,
    KubeVirt: DEFAULT_KUBEVIRT_CONDITIONS,
    CDI: DEFAULT_RESOURCE_CONDITIONS,
    SSP: DEFAULT_RESOURCE_CONDITIONS,
    NetworkAddonsConfig: DEFAULT_RESOURCE_CONDITIONS,
}
MACHINE_CONFIG_PODS_TO_COLLECT = ["machine-config-operator", "machine-config-daemon"]
