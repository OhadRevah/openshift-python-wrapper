import logging

import pytest
from ocp_resources.resource import ResourceEditor

from utilities.network import (
    DEPLOY_OVS,
    verify_ovs_installed_with_annotations,
    wait_for_ovs_daemonset_deleted,
    wait_for_ovs_pods,
    wait_for_ovs_status,
)


LOGGER = logging.getLogger()


def wait_for_ovs_removed(admin_client, ovs_daemonset, network_addons_config):
    wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
    wait_for_ovs_daemonset_deleted(ovs_daemonset=ovs_daemonset)
    wait_for_ovs_pods(
        admin_client=admin_client,
        hco_namespace=ovs_daemonset.namespace,
    )


@pytest.fixture()
def hyperconverged_ovs_annotations_disabled(
    hyperconverged_resource,
    network_addons_config,
    hyperconverged_ovs_annotations_enabled,
):
    with ResourceEditor(
        patches={
            hyperconverged_resource: {
                "metadata": {"annotations": {DEPLOY_OVS: "false"}}
            }
        }
    ):
        yield


@pytest.fixture()
def hyperconverged_ovs_annotations_removed(
    hyperconverged_resource,
    network_addons_config,
    hyperconverged_ovs_annotations_enabled,
):
    with ResourceEditor(
        patches={
            hyperconverged_resource: {"metadata": {"annotations": {DEPLOY_OVS: None}}}
        }
    ):
        yield


class TestOVSOptIn:
    @pytest.mark.polarion("CNV-5520")
    def test_ovs_installed(
        self,
        admin_client,
        network_addons_config,
        hyperconverged_ovs_annotations_enabled,
        hyperconverged_ovs_annotations_fetched,
    ):
        verify_ovs_installed_with_annotations(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled,
            hyperconverged_ovs_annotations_fetched=hyperconverged_ovs_annotations_fetched,
            network_addons_config=network_addons_config,
        )

    @pytest.mark.polarion("CNV-5533")
    def test_ovs_not_installed_annotations_removed(
        self,
        admin_client,
        network_addons_config,
        hyperconverged_ovs_annotations_enabled,
        hyperconverged_ovs_annotations_removed,
    ):
        wait_for_ovs_removed(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled,
            network_addons_config=network_addons_config,
        )

    @pytest.mark.polarion("CNV-5531")
    def test_ovs_not_installed_annotations_disabled(
        self,
        admin_client,
        network_addons_config,
        hyperconverged_ovs_annotations_enabled,
        hyperconverged_ovs_annotations_disabled,
    ):
        wait_for_ovs_removed(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled,
            network_addons_config=network_addons_config,
        )
