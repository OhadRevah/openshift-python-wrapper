import logging

import pytest

from tests.install_upgrade_operators.node_component.utils import (
    CNV_INFRA_PODS_COMPONENTS,
    CNV_WORKLOADS_PODS_COMPONENTS,
    NODE_PLACEMENT_INFRA,
    NODE_PLACEMENT_WORKLOADS,
    verify_components_exist_only_on_selected_node,
)


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "hyperconverged_with_node_placement",
    [
        {"infra": NODE_PLACEMENT_INFRA, "workloads": NODE_PLACEMENT_WORKLOADS},
    ],
    indirect=True,
)
@pytest.mark.usefixtures("node_placement_labels", "hyperconverged_with_node_placement")
class TestCreateHCOWithNodePlacement:
    @pytest.mark.polarion("CNV-5368")
    @pytest.mark.dependency(name="test_hco_cr_with_node_placement")
    def test_hco_cr_with_node_placement(
        self,
        hco_pods_per_nodes,
        nodes_labeled,
        expected_node_by_label,
        admin_client,
        hco_namespace,
    ):
        """
        "test_hco_cr_with_node_placement" test case check HyperConverged CR created with infra
        and workloads label.
        Verify that all the infrastructure and workloads Pod will be deployed on labeled nodes.
        """

        assert nodes_labeled["infra1"] == expected_node_by_label["infra1"]
        # Verify all Infra Pods are created on Node which has infra1 label on it.
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes,
            component_list=CNV_INFRA_PODS_COMPONENTS,
            selected_node=nodes_labeled["infra1"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

        assert nodes_labeled["work2"] == expected_node_by_label["work2"]
        # Verify all Workloads Pods are created on Node which has work2 label on it.
        verify_components_exist_only_on_selected_node(
            hco_pods_per_nodes=hco_pods_per_nodes,
            component_list=CNV_WORKLOADS_PODS_COMPONENTS,
            selected_node=nodes_labeled["work2"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5369")
    @pytest.mark.dependency(depends=["test_hco_cr_with_node_placement"])
    def test_node_placement_propagated_to_ssp_cr(
        self,
        ssp_cr_spec,
        virt_template_validator_spec_nodeselector,
    ):
        """
        This test we are going to check the HCO CR node placement
        propagated to SSP CR and then cascade to deployment 'virt-template-validator'.
        """

        assert (
            ssp_cr_spec["templateValidator"]["placement"]
            == NODE_PLACEMENT_INFRA["nodePlacement"]
        )

        # Verify that node placement configuration has been correctly
        # propagated to 'virt-template-validator' deployment
        assert (
            virt_template_validator_spec_nodeselector
            == NODE_PLACEMENT_INFRA["nodePlacement"]["nodeSelector"]
        )

    @pytest.mark.polarion("CNV-5381")
    @pytest.mark.dependency(depends=["test_hco_cr_with_node_placement"])
    def test_node_placement_propagated_to_vm_import_cr(
        self,
        vm_import_configs_spec,
        vm_import_controller_spec_nodeselector,
    ):
        """
        In this test case, check the HCO CR node placement
        propagated to VMImportConfig CR deployments 'VMImportConfig'.
        """
        # Verify VMImportConfig component spec
        assert (
            vm_import_configs_spec.get("infra") == NODE_PLACEMENT_INFRA["nodePlacement"]
        )

        # Verify that node placement configuration has been correctly
        # propagated to 'vm-import-controller' deployment
        assert (
            vm_import_controller_spec_nodeselector
            == NODE_PLACEMENT_INFRA["nodePlacement"]["nodeSelector"]
        )

    @pytest.mark.polarion("CNV-5382")
    @pytest.mark.dependency(depends=["test_hco_cr_with_node_placement"])
    def test_node_placement_propagated_to_network_addons_cr(
        self,
        network_addon_config_spec_placement,
        network_daemonsets_placement_list,
        network_deployment_placement_list,
    ):
        """
        In this test case, check the HCO CR node placement
        propagated to NetworkAddonsConfig CR and it's Daemonsets and Deployments.
        """
        # Verify NetworkAddonsConfig component spec for Infra and Workloads.
        assert (
            network_addon_config_spec_placement.get("infra")
            == NODE_PLACEMENT_INFRA["nodePlacement"]
        )
        assert (
            network_addon_config_spec_placement.get("workloads")
            == NODE_PLACEMENT_WORKLOADS["nodePlacement"]
        )

        # Verify that node placement configuration has been correctly
        # propagated to network related daemonsets
        for network_daemonsets_placement in network_daemonsets_placement_list:
            assert (
                network_daemonsets_placement
                == NODE_PLACEMENT_WORKLOADS["nodePlacement"]["nodeSelector"]
            )

        # Verify that node placement configuration has been correctly
        # propagated to network related deployments
        for network_deployment_placement in network_deployment_placement_list:
            assert (
                network_deployment_placement
                == NODE_PLACEMENT_INFRA["nodePlacement"]["nodeSelector"]
            )

    @pytest.mark.polarion("CNV-5383")
    @pytest.mark.dependency(depends=["test_hco_cr_with_node_placement"])
    def test_node_placement_propagated_to_kubevirt_cr(
        self,
        kubevirt_hyperconverged_spec_scope_function,
        virt_daemonset_nodeselector_comp,
        virt_deployment_nodeselector_comp_list,
    ):
        """
        In this test case, check the HCO CR node placement
        propagated to KubeVirt CR and it's daemonsets and deployments.
        """
        # Verify KubeVirt component spec for Infra and Workloads.
        assert (
            kubevirt_hyperconverged_spec_scope_function.get("infra").get(
                "nodePlacement"
            )
            == NODE_PLACEMENT_INFRA["nodePlacement"]
        )
        assert (
            kubevirt_hyperconverged_spec_scope_function.get("workloads").get(
                "nodePlacement"
            )
            == NODE_PLACEMENT_WORKLOADS["nodePlacement"]
        )

        # Verify that node placement configuration has been correctly
        # propagated to virt related daemonsets
        assert (
            virt_daemonset_nodeselector_comp
            == NODE_PLACEMENT_WORKLOADS["nodePlacement"]["nodeSelector"]["work-comp"]
        )

        # Verify that node placement configuration has been correctly
        # propagated to virt related deployments
        for virt_deployment_nodeselector_comp in virt_deployment_nodeselector_comp_list:
            assert (
                virt_deployment_nodeselector_comp
                == NODE_PLACEMENT_INFRA["nodePlacement"]["nodeSelector"]["infra-comp"]
            )

    @pytest.mark.polarion("CNV-5384")
    @pytest.mark.dependency(depends=["test_hco_cr_with_node_placement"])
    def test_node_placement_propagated_to_cdi_cr(
        self,
        cdi_spec,
        cdi_deployment_nodeselector_list,
    ):
        """
        In this test case, check the HCO CR node placement
        propagated to CDI CR and it's deployments.
        """
        # Verify CDI component spec for Infra and Workloads.
        assert cdi_spec.get("infra") == NODE_PLACEMENT_INFRA["nodePlacement"]
        assert cdi_spec.get("workload") == NODE_PLACEMENT_WORKLOADS["nodePlacement"]

        # Verify that node placement configuration has been correctly
        # propagated to CDI related deployments
        for cdi_deployment_nodeselector in cdi_deployment_nodeselector_list:
            assert (
                cdi_deployment_nodeselector
                == NODE_PLACEMENT_INFRA["nodePlacement"]["nodeSelector"]
            )