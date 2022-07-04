import os


# Paths to files
KUBECONFIG_SOURCE = os.environ.get("KUBECONFIG")
CONFIG_FILE_SOURCE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "manifests/kraken_config.yaml"
)
SCENARIOS_PATH_SOURCE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "manifests/"
)
# Constants for the Kraken container mounts
KUBECONFIG_TARGET = "/root/.kube/config"
CONFIG_FILE_TARGET = "/root/kraken/config/config.yaml"
SCENARIOS_PATH_TARGET = "/root/kraken/scenarios"
MOUNT_TYPE_BIND = "bind"
MOUNTS = [
    {
        "type": MOUNT_TYPE_BIND,
        "source": KUBECONFIG_SOURCE,
        "target": KUBECONFIG_TARGET,
    },
    {
        "type": MOUNT_TYPE_BIND,
        "source": CONFIG_FILE_SOURCE,
        "target": CONFIG_FILE_TARGET,
    },
    {
        "type": MOUNT_TYPE_BIND,
        "source": SCENARIOS_PATH_SOURCE,
        "target": SCENARIOS_PATH_TARGET,
    },
]
# Kraken container config constants
KRAKEN_IMAGE = "quay.io/chaos-kubox/krkn:latest"
NETWORK_MODE_HOST = "host"
PLATFORM_LINUX = "linux"
# Chaos resources constants
LITMUS_NAMESPACE = "litmus"
CHAOS_NAMESPACE = "chaos"
LITMUS_SERVICE_ACCOUNT = "litmus-sa"
VM_LABEL_KEY = "vm-label"
VM_LABEL_VALUE = "chaos-vm"
VM_LABEL = {VM_LABEL_KEY: VM_LABEL_VALUE}
# ChaosEngine constants
CHAOS_ENGINE_FILE = "chaosengine.yaml"
CHAOS_ENGINE_NAME = "chaos-engine"


# Litmus experiments
class ExperimentNames:
    POD_DELETE = "pod-delete"
