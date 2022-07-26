import os


# Paths to files
KUBECONFIG_PATH = os.environ.get("KUBECONFIG")
CHAOS_MANIFESTS_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "manifests/"
)
CHAOS_ENGINE_FILE_PATH = os.path.join(CHAOS_MANIFESTS_PATH, "chaosengine.yaml")
KRKN_CONFIG_PATH = os.path.join(CHAOS_MANIFESTS_PATH, "krkn_config.yaml")
KRKN_BASE_CONFIG_PATH = os.path.join(CHAOS_MANIFESTS_PATH, "krkn_base_config.yaml")

# Krkn repo constants
KRKN_REPO = "https://github.com/redhat-chaos/krkn.git"

# Chaos resources constants
LITMUS_NAMESPACE = "litmus"
CHAOS_NAMESPACE = "chaos"

LITMUS_SERVICE_ACCOUNT = "litmus-sa"

VM_LABEL_KEY = "vm-label"
VM_LABEL_VALUE = "chaos-vm"
VM_LABEL = {VM_LABEL_KEY: VM_LABEL_VALUE}

CHAOS_ENGINE_NAME = "chaos-engine"


# Litmus experiments
class ExperimentNames:
    POD_DELETE = "pod-delete"
