import logging

import pytest
from ocp_resources.resource import ResourceEditor
from openshift.dynamic.exceptions import ForbiddenError

from tests.install_upgrade_operators.node_component.utils import (
    INFRA_LABEL_1,
    INFRA_LABEL_2,
    INFRA_LABEL_3,
    INFRA_PODS_COMPONENTS,
    OPERATOR_PODS_COMPONENTS,
    SUBSCRIPTION_NODE_SELCTOR_1,
    SUBSCRIPTION_NODE_SELCTOR_2,
    SUBSCRIPTION_NODE_SELCTOR_3,
    SUBSCRIPTION_TOLERATIONS,
    WORK_LABEL_1,
    WORK_LABEL_2,
    WORK_LABEL_3,
    WORKLOADS_PODS_COMPONENTS,
    verify_components_exist_only_on_selected_node,
)


LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures(
    "node_placement_labels",
    "hyperconverged_resource_before_np",
    "cnv_sub_resource_before_np",
)
class TestDeployCNVOnSubsetOfClusterNodes:
    @pytest.mark.polarion("CNV-5226")
    @pytest.mark.parametrize(
        "alter_cnv_sub_configuration",
        [
            {
                "node_selector": SUBSCRIPTION_NODE_SELCTOR_2,
                "tolerations": SUBSCRIPTION_TOLERATIONS,
            }
        ],
        indirect=True,
    )
    def test_change_subscription_on_selected_node_before_workload(
        self,
        alter_cnv_sub_configuration,
        subscription_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["op2"] == expected_node_by_label["op2"]
        # Verify all the operators are moved to master-1
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=subscription_pods_per_nodes_after_altering_placement,
            component_list=OPERATOR_PODS_COMPONENTS,
            selected_node=nodes_labeled["op2"][0],
        )

    @pytest.mark.polarion("CNV-5228")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_2, "workloads": WORK_LABEL_1},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_change_infrastructure_components_on_selected_node_before_workload"
    )
    def test_change_infrastructure_components_on_selected_node_before_workload(
        self,
        hco_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["infra2"] == expected_node_by_label["infra2"]
        # Verify all Infra components are moved to worker-2.
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes_after_altering_placement,
            component_list=INFRA_PODS_COMPONENTS,
            selected_node=nodes_labeled["infra2"][0],
        )

    @pytest.mark.polarion("CNV-5229")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_2, "workloads": WORK_LABEL_3},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_change_workload_components_on_selected_node_before_workload",
        depends=[
            "test_change_infrastructure_components_on_selected_node_before_workload"
        ],
    )
    def test_change_workload_components_on_selected_node_before_workload(
        self,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["work3"] == expected_node_by_label["work3"]

        # Verify all Workloads Pods are moved to worker-3.
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes_after_altering_placement,
            component_list=WORKLOADS_PODS_COMPONENTS,
            selected_node=nodes_labeled["work3"][0],
        )

    @pytest.mark.polarion("CNV-5230")
    @pytest.mark.dependency(
        name="test_deploying_workloads_on_selected_nodes",
        depends=["test_change_workload_components_on_selected_node_before_workload"],
    )
    def test_deploying_workloads_on_selected_nodes(
        self,
        vm_placement_vm_work3,
        nodes_labeled,
    ):
        assert vm_placement_vm_work3.vmi.node.name == nodes_labeled["work3"][0]

    @pytest.mark.polarion("CNV-5231")
    @pytest.mark.dependency(
        depends=["test_deploying_workloads_on_selected_nodes"],
    )
    def test_workload_components_selection_change_denied_with_workloads(
        self,
        nodes_labeled,
        admin_client,
        hco_namespace,
        vm_placement_vm_work3,
        hyperconverged_resource,
    ):
        LOGGER.info(
            "Attempting to update HCO with node placement, expecting it to fail"
        )
        with pytest.raises(
            ForbiddenError, match=r"denied the request:.*while there are running vms"
        ):
            with ResourceEditor(
                patches={hyperconverged_resource: {"spec": {"workloads": WORK_LABEL_1}}}
            ):
                pytest.fail("Workloads label changed while VM/Workload is present.")

    @pytest.mark.polarion("CNV-5232")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_1},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_infrastructure_components_selection_change_allowed_with_workloads",
        depends=["test_deploying_workloads_on_selected_nodes"],
    )
    def test_infrastructure_components_selection_change_allowed_with_workloads(
        self,
        vm_placement_vm_work3,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["infra1"] == expected_node_by_label["infra1"]
        # Verify all infra components are removed from worker-2 and created on worker-1.
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes_after_altering_placement,
            component_list=INFRA_PODS_COMPONENTS,
            selected_node=nodes_labeled["infra1"][0],
        )

    @pytest.mark.polarion("CNV-5233")
    @pytest.mark.parametrize(
        "alter_cnv_sub_configuration",
        [
            {
                "node_selector": SUBSCRIPTION_NODE_SELCTOR_3,
                "tolerations": SUBSCRIPTION_TOLERATIONS,
            }
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        depends=[
            "test_infrastructure_components_selection_change_allowed_with_workloads"
        ],
    )
    def test_operator_components_selection_change_allowed_with_workloads(
        self,
        vm_placement_vm_work3,
        alter_cnv_sub_configuration,
        subscription_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["op3"] == expected_node_by_label["op3"]
        # Verify all the operators are moved to master-2
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=subscription_pods_per_nodes_after_altering_placement,
            component_list=OPERATOR_PODS_COMPONENTS,
            selected_node=nodes_labeled["op3"][0],
        )

    @pytest.mark.polarion("CNV-5236")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_3},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_infrastructure_components_selection_change_allowed_after_workloads",
        depends=[
            "test_infrastructure_components_selection_change_allowed_with_workloads"
        ],
    )
    def test_infrastructure_components_selection_change_allowed_after_workloads(
        self,
        delete_vm_after_placement,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["infra3"] == expected_node_by_label["infra3"]
        # Verify all infrastructure components are removed from worker-1 and created on worker-3
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes_after_altering_placement,
            component_list=WORKLOADS_PODS_COMPONENTS,
            selected_node=nodes_labeled["infra3"][0],
        )

    @pytest.mark.polarion("CNV-5237")
    @pytest.mark.parametrize(
        "alter_cnv_sub_configuration",
        [
            {
                "node_selector": SUBSCRIPTION_NODE_SELCTOR_1,
                "tolerations": SUBSCRIPTION_TOLERATIONS,
            }
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        depends=[
            "test_infrastructure_components_selection_change_allowed_after_workloads"
        ],
    )
    def test_operator_components_selection_change_allowed_after_workloads(
        self,
        alter_cnv_sub_configuration,
        subscription_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["op1"] == expected_node_by_label["op1"]
        # Verify all the operators are moved to master-0
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=subscription_pods_per_nodes_after_altering_placement,
            component_list=OPERATOR_PODS_COMPONENTS,
            selected_node=nodes_labeled["op1"][0],
        )

    @pytest.mark.polarion("CNV-5235")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"workloads": WORK_LABEL_2},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        depends=[
            "test_infrastructure_components_selection_change_allowed_after_workloads"
        ],
    )
    def test_workload_components_selection_change_allowed_after_workloads(
        self,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["work2"] == expected_node_by_label["work2"]
        # Verify all workloads components are removed from worker-3 and created on worker-2
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes_after_altering_placement,
            component_list=WORKLOADS_PODS_COMPONENTS,
            selected_node=nodes_labeled["work2"][0],
        )
