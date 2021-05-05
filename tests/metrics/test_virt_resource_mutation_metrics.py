import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.configmap import ConfigMap
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.console_quick_starts import ConsoleQuickStart
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.priority_class import PriorityClass
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.service import Service
from ocp_resources.service_monitor import ServiceMonitor
from ocp_resources.ssp import SSP
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine_import_configs import VMImportConfig

from tests.metrics.utils import (
    get_all_hco_cr_modification_alert,
    get_changed_mutation_component_value,
    get_hco_cr_modification_alert_state,
)


LOGGER = logging.getLogger(__name__)


COMPONENT_NAMES = {
    "ssp": {
        "comp_name": "ssp/ssp-kubevirt-hyperconverged",
        "resource_info": {"resource": SSP},
    },
    "kubevirt": {
        "comp_name": "kubevirt/kubevirt-kubevirt-hyperconverged",
        "resource_info": {"resource": KubeVirt},
    },
    "cdi": {
        "comp_name": "cdi/cdi-kubevirt-hyperconverged",
        "resource_info": {"resource": CDI},
    },
    "cluster": {
        "comp_name": "networkaddonsconfig/cluster",
        "resource_info": {"resource": NetworkAddonsConfig},
    },
    "vmimportconfig": {
        "comp_name": "vmimportconfig/vmimport-kubevirt-hyperconverged",
        "resource_info": {"resource": VMImportConfig},
    },
    "config_map": {
        "comp_name": [
            "configmap/kubevirt-storage-class-defaults",
            "configmap/v2v-vmware",
        ],
    },
    "priority_class": {
        "comp_name": "priorityclass/kubevirt-cluster-critical",
        "resource_info": {
            "name": "kubevirt-cluster-critical",
            "resource": PriorityClass,
        },
    },
    "console_cli_download": {
        "comp_name": "consoleclidownload/virtctl-clidownloads-kubevirt-hyperconverged",
        "resource_info": {
            "name": "virtctl-clidownloads-kubevirt-hyperconverged",
            "resource": ConsoleCLIDownload,
        },
    },
    "prometheus_rule": {
        "comp_name": "prometheusrule/prometheus_rule",
        "resource_info": {
            "name": "kubevirt-hyperconverged-prometheus-rule",
            "resource": PrometheusRule,
        },
    },
    "service_monitor": {
        "comp_name": "servicemonitor/kubevirt-hyperconverged-operator-metrics",
        "resource_info": {
            "name": "kubevirt-hyperconverged-operator-metrics",
            "resource": ServiceMonitor,
        },
    },
    "service": {
        "comp_name": "service/kubevirt-hyperconverged-operator-metrics",
        "resource_info": {
            "name": "kubevirt-hyperconverged-operator-metrics",
            "resource": Service,
        },
    },
    "console_quick_start": {
        "comp_name": [
            "consolequickstart/connect-ext-net-to-vm",
            "consolequickstart/create-win10-vm",
            "consolequickstart/create-rhel-vm",
            "consolequickstart/import-vmware-vm",
        ]
    },
}


@pytest.mark.parametrize(
    "mutation_count_before_change, updated_resource_with_invalid_label, component_name",
    [
        pytest.param(
            COMPONENT_NAMES["ssp"]["comp_name"],
            COMPONENT_NAMES["ssp"]["resource_info"],
            COMPONENT_NAMES["ssp"]["comp_name"],
            id="ssp",
            marks=(pytest.mark.polarion("CNV-6129")),
        ),
        pytest.param(
            COMPONENT_NAMES["console_cli_download"]["comp_name"],
            COMPONENT_NAMES["console_cli_download"]["resource_info"],
            COMPONENT_NAMES["console_cli_download"]["comp_name"],
            id="console_cli_download",
            marks=(pytest.mark.polarion("CNV-6130")),
        ),
        pytest.param(
            COMPONENT_NAMES["priority_class"]["comp_name"],
            COMPONENT_NAMES["priority_class"]["resource_info"],
            COMPONENT_NAMES["priority_class"]["comp_name"],
            id="priority_class",
            marks=(pytest.mark.polarion("CNV-6131")),
        ),
        pytest.param(
            COMPONENT_NAMES["kubevirt"]["comp_name"],
            COMPONENT_NAMES["kubevirt"]["resource_info"],
            COMPONENT_NAMES["kubevirt"]["comp_name"],
            id="kubevirt",
            marks=(pytest.mark.polarion("CNV-6132")),
        ),
        pytest.param(
            COMPONENT_NAMES["cdi"]["comp_name"],
            COMPONENT_NAMES["cdi"]["resource_info"],
            COMPONENT_NAMES["cdi"]["comp_name"],
            id="cdi",
            marks=(pytest.mark.polarion("CNV-6133")),
        ),
        pytest.param(
            COMPONENT_NAMES["config_map"]["comp_name"][0],
            {"resource": ConfigMap, "name": "kubevirt-storage-class-defaults"},
            COMPONENT_NAMES["config_map"]["comp_name"][0],
            id="config_map_storage_class",
            marks=(pytest.mark.polarion("CNV-6134")),
        ),
        pytest.param(
            COMPONENT_NAMES["config_map"]["comp_name"][1],
            {"resource": ConfigMap, "name": "v2v-vmware"},
            COMPONENT_NAMES["config_map"]["comp_name"][1],
            id="config_map_v2v_vmware",
            marks=(pytest.mark.polarion("CNV-6560")),
        ),
        pytest.param(
            COMPONENT_NAMES["cluster"]["comp_name"],
            COMPONENT_NAMES["cluster"]["resource_info"],
            COMPONENT_NAMES["cluster"]["comp_name"],
            id="networkaddonsconfig",
            marks=(pytest.mark.polarion("CNV-6135")),
        ),
        pytest.param(
            COMPONENT_NAMES["vmimportconfig"]["comp_name"],
            COMPONENT_NAMES["vmimportconfig"]["resource_info"],
            COMPONENT_NAMES["vmimportconfig"]["comp_name"],
            id="vmimportconfig",
            marks=(pytest.mark.polarion("CNV-6136")),
        ),
        pytest.param(
            COMPONENT_NAMES["service"]["comp_name"],
            COMPONENT_NAMES["service"]["resource_info"],
            COMPONENT_NAMES["service"]["comp_name"],
            id="service",
            marks=(pytest.mark.polarion("CNV-6137")),
        ),
        pytest.param(
            COMPONENT_NAMES["service_monitor"]["comp_name"],
            COMPONENT_NAMES["service_monitor"]["resource_info"],
            COMPONENT_NAMES["service_monitor"]["comp_name"],
            id="service_monitor",
            marks=(pytest.mark.polarion("CNV-6138")),
        ),
        pytest.param(
            COMPONENT_NAMES["prometheus_rule"]["comp_name"],
            COMPONENT_NAMES["prometheus_rule"]["resource_info"],
            COMPONENT_NAMES["prometheus_rule"]["comp_name"],
            id="prometheus_rule",
            marks=(pytest.mark.polarion("CNV-6139")),
        ),
        pytest.param(
            COMPONENT_NAMES["console_quick_start"]["comp_name"][0],
            {"resource": ConsoleQuickStart, "name": "connect-ext-net-to-vm"},
            COMPONENT_NAMES["console_quick_start"]["comp_name"][0],
            id="console_quick_start_connect_ext_net_to_vm",
            marks=(pytest.mark.polarion("CNV-6140")),
        ),
        pytest.param(
            COMPONENT_NAMES["console_quick_start"]["comp_name"][1],
            {"resource": ConsoleQuickStart, "name": "create-win10-vm"},
            COMPONENT_NAMES["console_quick_start"]["comp_name"][1],
            id="console_quick_start_create_win_10_vm",
            marks=(pytest.mark.polarion("CNV-6141")),
        ),
        pytest.param(
            COMPONENT_NAMES["console_quick_start"]["comp_name"][2],
            {"resource": ConsoleQuickStart, "name": "create-rhel-vm"},
            COMPONENT_NAMES["console_quick_start"]["comp_name"][2],
            id="console_quick_start_create_rhel_vm",
            marks=(pytest.mark.polarion("CNV-6142")),
        ),
        pytest.param(
            COMPONENT_NAMES["console_quick_start"]["comp_name"][3],
            {"resource": ConsoleQuickStart, "name": "import-vmware-vm"},
            COMPONENT_NAMES["console_quick_start"]["comp_name"][3],
            id="console_quick_start_import_vmware_vm",
            marks=(pytest.mark.polarion("CNV-6143")),
        ),
    ],
    indirect=[
        "updated_resource_with_invalid_label",
        "mutation_count_before_change",
    ],
)
@pytest.mark.dependency(name="test_metric_invalid_change")
def test_metric_invalid_change(
    prometheus,
    mutation_count_before_change,
    updated_resource_with_invalid_label,
    component_name,
):
    """
    Any single change to Kubevirt spec will trigger the kubevirt_hco_out_of_band_modifications_count' metrics with
    component name with it's value.
    """
    mutation_count_after_change = get_changed_mutation_component_value(
        prometheus=prometheus,
        component_name=component_name,
        previous_value=mutation_count_before_change,
    )
    assert (
        mutation_count_after_change - mutation_count_before_change == 1
    ), f"'{component_name}' Count before '{mutation_count_before_change}',and after '{mutation_count_after_change}'"

    # Check an alert state is firing after metric is generated.
    alert_state = get_hco_cr_modification_alert_state(
        prometheus=prometheus, component_name=component_name
    )
    assert (
        alert_state == "firing"
    ), f"Alert is not in the state of firing for '{component_name}', current state is '{alert_state}'."


@pytest.mark.dependency(depends=["test_metric_invalid_change"])
@pytest.mark.polarion("CNV-6144")
def test_check_no_single_alert_remain(prometheus):
    # Wait until alert is removed.
    samples = TimeoutSampler(
        wait_timeout=630,
        sleep=10,
        func=get_all_hco_cr_modification_alert,
        prometheus=prometheus,
    )
    alerts_present = []
    try:
        for alert_present in samples:
            if not alert_present:
                break
    except TimeoutExpiredError:
        LOGGER.error(
            f"There are still alerts present after 10 minutes {alerts_present}"
        )
        raise
