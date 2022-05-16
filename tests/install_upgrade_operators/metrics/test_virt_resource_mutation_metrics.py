import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.configmap import ConfigMap
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.console_quick_start import ConsoleQuickStart
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.priority_class import PriorityClass
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.service import Service
from ocp_resources.service_monitor import ServiceMonitor
from ocp_resources.ssp import SSP
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.metrics.utils import (
    get_all_hco_cr_modification_alert,
    get_changed_mutation_component_value,
    get_hco_cr_modification_alert_state,
    wait_for_summary_count_to_be_expected,
)
from utilities.constants import CDI_KUBEVIRT_HYPERCONVERGED, SSP_KUBEVIRT_HYPERCONVERGED


pytestmark = pytest.mark.sno
LOGGER = logging.getLogger(__name__)
COUNT_FIVE = 5
COUNT_THREE = 3
COUNT_TWO = 2

COMPONENT_CONFIG = {
    "ssp": {
        "resource_info": {
            "comp_name": f"ssp/{SSP_KUBEVIRT_HYPERCONVERGED}",
            "name": SSP_KUBEVIRT_HYPERCONVERGED,
            "resource": SSP,
            "count": COUNT_FIVE,
        },
    },
    "kubevirt": {
        "resource_info": {
            "comp_name": "kubevirt/kubevirt-kubevirt-hyperconverged",
            "name": "kubevirt-kubevirt-hyperconverged",
            "resource": KubeVirt,
            "count": COUNT_FIVE,
        },
    },
    "cdi": {
        "resource_info": {
            "comp_name": f"cdi/{CDI_KUBEVIRT_HYPERCONVERGED}",
            "name": "cdi-kubevirt-hyperconverged",
            "resource": CDI,
            "count": COUNT_FIVE,
        },
    },
    "cluster": {
        "resource_info": {
            "comp_name": "networkaddonsconfig/cluster",
            "name": "cluster",
            "resource": NetworkAddonsConfig,
            "count": COUNT_TWO,
        },
    },
    "config_map_kubevirt_storage": {
        "resource_info": {
            "comp_name": "configmap/kubevirt-storage-class-defaults",
            "resource": ConfigMap,
            "name": "kubevirt-storage-class-defaults",
            "count": COUNT_TWO,
        },
    },
    "priority_class": {
        "resource_info": {
            "comp_name": "priorityclass/kubevirt-cluster-critical",
            "name": "kubevirt-cluster-critical",
            "resource": PriorityClass,
            "count": COUNT_FIVE,
        },
    },
    "console_cli_download": {
        "resource_info": {
            "comp_name": "consoleclidownload/virtctl-clidownloads-kubevirt-hyperconverged",
            "name": "virtctl-clidownloads-kubevirt-hyperconverged",
            "resource": ConsoleCLIDownload,
            "count": COUNT_TWO,
        },
    },
    "prometheus_rule": {
        "resource_info": {
            "comp_name": "prometheusrule/kubevirt-hyperconverged-prometheus-rule",
            "name": "kubevirt-hyperconverged-prometheus-rule",
            "resource": PrometheusRule,
            "count": COUNT_THREE,
        },
    },
    "service_monitor": {
        "resource_info": {
            "comp_name": "servicemonitor/kubevirt-hyperconverged-operator-metrics",
            "name": "kubevirt-hyperconverged-operator-metrics",
            "resource": ServiceMonitor,
            "count": COUNT_TWO,
        },
    },
    "service": {
        "resource_info": {
            "comp_name": "service/kubevirt-hyperconverged-operator-metrics",
            "name": "kubevirt-hyperconverged-operator-metrics",
            "resource": Service,
            "count": COUNT_THREE,
        },
    },
    "console_quick_start_net_to_vm": {
        "resource_info": {
            "comp_name": "consolequickstart/connect-ext-net-to-vm",
            "resource": ConsoleQuickStart,
            "name": "connect-ext-net-to-vm",
            "count": COUNT_TWO,
        },
    },
    "console_quick_start_create_win10_vm": {
        "resource_info": {
            "comp_name": "consolequickstart/create-win10-vm",
            "resource": ConsoleQuickStart,
            "name": "create-win10-vm",
            "count": COUNT_TWO,
        },
    },
    "console_quick_start_create_rhel_vm": {
        "resource_info": {
            "comp_name": "consolequickstart/create-rhel-vm",
            "resource": ConsoleQuickStart,
            "name": "create-rhel-vm",
            "count": COUNT_TWO,
        },
    },
}


@pytest.mark.parametrize(
    "mutation_count_before_change, updated_resource_with_invalid_label, component_name",
    [
        pytest.param(
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["ssp"]["resource_info"],
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            id="ssp",
            marks=(pytest.mark.polarion("CNV-6129")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            id="console_cli_download",
            marks=(pytest.mark.polarion("CNV-6130")),
        ),
        pytest.param(
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["priority_class"]["resource_info"],
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            id="priority_class",
            marks=pytest.mark.polarion("CNV-6131"),
        ),
        pytest.param(
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            id="kubevirt",
            marks=(pytest.mark.polarion("CNV-6132")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cdi"]["resource_info"],
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            id="cdi",
            marks=(pytest.mark.polarion("CNV-6133")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cluster"]["resource_info"],
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            id="networkaddonsconfig",
            marks=(pytest.mark.polarion("CNV-6135")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service"]["resource_info"],
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            id="service",
            marks=(pytest.mark.polarion("CNV-6137")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            id="service_monitor",
            marks=(pytest.mark.polarion("CNV-6138")),
        ),
        pytest.param(
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            id="prometheus_rule",
            marks=(pytest.mark.polarion("CNV-6139")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"][
                "comp_name"
            ],
            id="console_quick_start_connect_ext_net_to_vm",
            marks=(pytest.mark.polarion("CNV-6140")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"][
                "comp_name"
            ],
            id="console_quick_start_create_win_10_vm",
            marks=(pytest.mark.polarion("CNV-6141")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"][
                "comp_name"
            ],
            id="console_quick_start_create_rhel_vm",
            marks=(pytest.mark.polarion("CNV-6142")),
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


@pytest.mark.parametrize(
    "mutation_count_before_change, updated_resource_multiple_times_with_invalid_label, component_name, change_count",
    [
        pytest.param(
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["ssp"]["resource_info"],
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["ssp"]["resource_info"]["count"],
            id="ssp",
            marks=(pytest.mark.polarion("CNV-6148")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["count"],
            id="console_cli_download",
            marks=(pytest.mark.polarion("CNV-6149")),
        ),
        pytest.param(
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["priority_class"]["resource_info"],
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["priority_class"]["resource_info"]["count"],
            id="priority_class",
            marks=pytest.mark.polarion("CNV-6150"),
        ),
        pytest.param(
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["count"],
            id="kubevirt",
            marks=(pytest.mark.polarion("CNV-6151")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cdi"]["resource_info"],
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cdi"]["resource_info"]["count"],
            id="cdi",
            marks=(pytest.mark.polarion("CNV-6152")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cluster"]["resource_info"],
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cluster"]["resource_info"]["count"],
            id="networkaddonsconfig",
            marks=(pytest.mark.polarion("CNV-6154")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service"]["resource_info"],
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service"]["resource_info"]["count"],
            id="service",
            marks=(pytest.mark.polarion("CNV-6156")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["count"],
            id="service_monitor",
            marks=(pytest.mark.polarion("CNV-6157")),
        ),
        pytest.param(
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["count"],
            id="prometheus_rule",
            marks=(pytest.mark.polarion("CNV-6158")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_net_to_vm"]["resource_info"]["count"],
            id="console_quick_start_connect_ext_net_to_vm",
            marks=(pytest.mark.polarion("CNV-6159")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_create_win10_vm"]["resource_info"][
                "count"
            ],
            id="console_quick_start_create_win_10_vm",
            marks=(pytest.mark.polarion("CNV-6160")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"][
                "comp_name"
            ],
            COMPONENT_CONFIG["console_quick_start_create_rhel_vm"]["resource_info"][
                "count"
            ],
            id="console_quick_start_create_rhel_vm",
            marks=(pytest.mark.polarion("CNV-6161")),
        ),
    ],
    indirect=[
        "updated_resource_multiple_times_with_invalid_label",
        "mutation_count_before_change",
    ],
)
@pytest.mark.dependency(name="test_metric_multiple_invalid_change")
def test_metric_multiple_invalid_change(
    prometheus,
    mutation_count_before_change,
    updated_resource_multiple_times_with_invalid_label,
    component_name,
    change_count,
):
    """
    Multiple time change to resource spec will trigger the kubevirt_hco_out_of_band_modifications_count' metrics with
    component name with it's summary.
    Alert "KubevirtHyperconvergedClusterOperatorCRModification" is generated
    for each component name with it's state and summary (integer).
    """
    mutation_count_after_change = get_changed_mutation_component_value(
        prometheus=prometheus,
        component_name=component_name,
        previous_value=mutation_count_before_change,
    )
    assert (
        mutation_count_after_change - mutation_count_before_change == change_count
    ), f"'{component_name}' Count before '{mutation_count_before_change}',and after '{mutation_count_after_change}'"

    # Check an alert state is firing after metric is generated.
    alert_state = get_hco_cr_modification_alert_state(
        prometheus=prometheus, component_name=component_name
    )
    assert (
        alert_state == "firing"
    ), f"Alert is not in the state of firing for '{component_name}', current state is '{alert_state}'."

    # Alert summary contains change to the component 'n' times where 'n' represents integer.
    alert_summary_with_count = wait_for_summary_count_to_be_expected(
        prometheus=prometheus,
        component_name=component_name,
        expected_summary_value=change_count,
    )
    # Check an alert summary updated with the 'n' times of invalid change.

    assert alert_summary_with_count == change_count


@pytest.mark.dependency(
    depends=["test_metric_invalid_change", "test_metric_multiple_invalid_change"]
)
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
