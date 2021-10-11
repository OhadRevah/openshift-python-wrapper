import copy

from ocp_resources.cdi import CDI
from ocp_resources.configmap import ConfigMap
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.console_quick_start import ConsoleQuickStart
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.priority_class import PriorityClass
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.resource import Resource
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.route import Route
from ocp_resources.service import Service
from ocp_resources.service_monitor import ServiceMonitor
from ocp_resources.ssp import SSP
from ocp_resources.vm_import_config import VMImportConfig


CLUSTER_SCOPE_RESOURCES = [
    "CDI",
    "NetworkAddonsConfig",
    "VMImportConfig",
    "ConsoleCLIDownload",
    "PriorityClass",
    "ConsoleQuickStart",
]
# components
COMPONENT_LABEL_TEMPLATING_VALUE = "templating"
COMPONENT_LABEL_MONITORING_VALUE = "monitoring"
COMPONENT_LABEL_SCHEDULE_VALUE = "schedule"
COMPONENT_LABEL_COMPUTE_VALUE = "compute"
COMPONENT_LABEL_IMPORT_VALUE = "import"
COMPONENT_LABEL_STORAGE_VALUE = "storage"
COMPONENT_LABEL_NETWORK_VALUE = "network"
# labels keys
MANAGED_BY_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"
VERSION_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/version"
COMPONENT_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/component"
PART_OF_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/part-of"
# labels values
MANAGED_BY_LABEL_VALUE_OLM = "olm"
HCO_MANAGED_BY_LABEL_VALUE = "hco-operator"
HCO_PART_OF_LABEL_VALUE = "hyperconverged-cluster"
# HCO
HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE = {
    MANAGED_BY_LABEL_KEY: HCO_MANAGED_BY_LABEL_VALUE,
    VERSION_LABEL_KEY: None,
    COMPONENT_LABEL_KEY: None,
    PART_OF_LABEL_KEY: HCO_PART_OF_LABEL_VALUE,
}
EXPECTED_TEMPLATING_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_TEMPLATING_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_TEMPLATING_VALUE
EXPECTED_SCHEDULE_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_SCHEDULE_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_SCHEDULE_VALUE
EXPECTED_MONITORING_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_MONITORING_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_MONITORING_VALUE
EXPECTED_NETWORK_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_NETWORK_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_NETWORK_VALUE
EXPECTED_IMPORT_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_IMPORT_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_IMPORT_VALUE
EXPECTED_STORAGE_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_STORAGE_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_STORAGE_VALUE
EXPECTED_COMPUTE_LABELS = copy.deepcopy(HCO_COMPONENTS_LABELS_EXPECTED_TEMPLATE)
EXPECTED_COMPUTE_LABELS[COMPONENT_LABEL_KEY] = COMPONENT_LABEL_COMPUTE_VALUE
ALL_EXPECTED_LABELS_DICTS = [
    EXPECTED_TEMPLATING_LABELS,
    EXPECTED_SCHEDULE_LABELS,
    EXPECTED_MONITORING_LABELS,
    EXPECTED_NETWORK_LABELS,
    EXPECTED_IMPORT_LABELS,
    EXPECTED_STORAGE_LABELS,
    EXPECTED_COMPUTE_LABELS,
]
# HCO components verification dict
EXPECTED_COMPONENT_LABELS_DICT_MAP = {
    ConsoleCLIDownload: {
        "virtctl-clidownloads-kubevirt-hyperconverged": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
    },
    PriorityClass: {
        "kubevirt-cluster-critical": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
    },
    KubeVirt: {
        "kubevirt-kubevirt-hyperconverged": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
    },
    CDI: {
        "cdi-kubevirt-hyperconverged": {
            "expected_labels": EXPECTED_STORAGE_LABELS,
        },
    },
    ConfigMap: {
        "kubevirt-storage-class-defaults": {
            "expected_labels": EXPECTED_STORAGE_LABELS,
        },
        "v2v-vmware": {
            "expected_labels": EXPECTED_IMPORT_LABELS,
        },
        "grafana-dashboard-kubevirt-top-consumers": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
            "namespace": "openshift-config-managed",
        },
    },
    NetworkAddonsConfig: {
        "cluster": {
            "expected_labels": EXPECTED_NETWORK_LABELS,
        },
    },
    VMImportConfig: {
        "vmimport-kubevirt-hyperconverged": {
            "expected_labels": EXPECTED_IMPORT_LABELS,
        },
    },
    SSP: {
        "ssp-kubevirt-hyperconverged": {
            "expected_labels": EXPECTED_SCHEDULE_LABELS,
        },
    },
    Service: {
        "kubevirt-hyperconverged-operator-metrics": {
            "expected_labels": EXPECTED_MONITORING_LABELS,
        },
        "hyperconverged-cluster-cli-download": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
    },
    ServiceMonitor: {
        "kubevirt-hyperconverged-operator-metrics": {
            "expected_labels": EXPECTED_MONITORING_LABELS,
        },
    },
    PrometheusRule: {
        "kubevirt-hyperconverged-prometheus-rule": {
            "expected_labels": EXPECTED_MONITORING_LABELS,
        },
    },
    Role: {
        "hco.kubevirt.io:config-reader": {
            "expected_labels": EXPECTED_STORAGE_LABELS,
        },
    },
    RoleBinding: {
        "hco.kubevirt.io:config-reader": {
            "expected_labels": EXPECTED_STORAGE_LABELS,
        },
    },
    ConsoleQuickStart: {
        "connect-ext-net-to-vm": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
        "create-win10-vm": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
        "create-rhel-vm": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
        "import-vmware-vm": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
    },
    Route: {
        "hyperconverged-cluster-cli-download": {
            "expected_labels": EXPECTED_COMPUTE_LABELS,
        },
    },
}
