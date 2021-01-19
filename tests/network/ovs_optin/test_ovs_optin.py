import logging

import pytest
from resources.resource import ResourceEditor

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


def updated_metadata(hyperconverged_resource, annotations):
    return {
        "metadata": {
            "annotations": annotations,
            "name": hyperconverged_resource.name,
            "resourceVersion": hyperconverged_resource.instance.metadata.resourceVersion,
        },
        "kind": hyperconverged_resource.kind,
        "apiVersion": hyperconverged_resource.api_version,
    }


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
    wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
    hyperconverged_ovs_annotations_enabled.wait_until_deployed()


@pytest.fixture()
def hyperconverged_ovs_annotations_removed(
    hyperconverged_resource,
    network_addons_config,
    hyperconverged_ovs_annotations_enabled,
):
    origin_annotations = hyperconverged_resource.instance.to_dict()["metadata"][
        "annotations"
    ]
    annotations = origin_annotations.copy()
    annotations.pop(DEPLOY_OVS)
    with ResourceEditor(
        patches={
            hyperconverged_resource: updated_metadata(
                hyperconverged_resource=hyperconverged_resource, annotations=annotations
            )
        },
        user_backups={
            hyperconverged_resource: updated_metadata(
                hyperconverged_resource=hyperconverged_resource,
                annotations=origin_annotations,
            )
        },
        action="replace",
    ):
        yield

    wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
    hyperconverged_ovs_annotations_enabled.wait_until_deployed()


class TestOVSOptIn:
    @pytest.mark.polarion("CNV-5520")
    def test_ovs_installed(
        self,
        admin_client,
        hyperconverged_ovs_annotations_enabled,
        hyperconverged_ovs_annotations_fetched,
        network_addons_config,
    ):
        verify_ovs_installed_with_annotations(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled,
            hyperconverged_ovs_annotations_fetched=hyperconverged_ovs_annotations_fetched,
            network_addons_config=network_addons_config,
        )

    @pytest.mark.polarion("CNV-5531")
    def test_ovs_not_installed_annotations_disabled(
        self,
        admin_client,
        hyperconverged_ovs_annotations_enabled,
        hyperconverged_ovs_annotations_disabled,
        network_addons_config,
    ):
        wait_for_ovs_removed(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled,
            network_addons_config=network_addons_config,
        )

    @pytest.mark.polarion("CNV-5533")
    def test_ovs_not_installed_annotations_removed(
        self,
        admin_client,
        hyperconverged_ovs_annotations_enabled,
        hyperconverged_ovs_annotations_removed,
        network_addons_config,
    ):
        wait_for_ovs_removed(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled,
            network_addons_config=network_addons_config,
        )
