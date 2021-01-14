import logging

import pytest
from resources.resource import ResourceEditor
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.network import OVS_DS_NAME, wait_for_ovs_pods, wait_for_ovs_status


LOGGER = logging.getLogger()
DEPLOY_OVS = "deployOVS"


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


def wait_for_ovs_daemonset_deleted(ovs_daemonset):
    samples = TimeoutSampler(timeout=90, sleep=1, func=lambda: ovs_daemonset.exists)
    try:
        for sample in samples:
            if not sample:
                return True

    except TimeoutExpiredError:
        LOGGER.error("OVD daemonset exists after opt-out")
        raise


@pytest.fixture()
def hyperconverged_ovs_annotations_disabled(
    hyperconverged_resource, network_addons_config, ovs_daemonset
):
    with ResourceEditor(
        patches={
            hyperconverged_resource: {
                "metadata": {"annotations": {DEPLOY_OVS: "False"}}
            }
        }
    ):
        yield
    wait_for_ovs_status(network_addons_config=network_addons_config, status=True)
    ovs_daemonset.wait_until_deployed()


@pytest.fixture()
def hyperconverged_ovs_annotations_removed(
    hyperconverged_resource, network_addons_config, ovs_daemonset
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

    wait_for_ovs_status(network_addons_config=network_addons_config, status=True)
    ovs_daemonset.wait_until_deployed()


class TestOVSOptIn:
    @pytest.mark.polarion("CNV-5520")
    def test_ovs_installed(
        self,
        admin_client,
        ovs_daemonset,
        network_addons_config,
    ):
        wait_for_ovs_status(network_addons_config=network_addons_config)
        assert ovs_daemonset.exists, f"{OVS_DS_NAME} not found"
        ovs_daemonset.wait_until_deployed()
        wait_for_ovs_pods(
            admin_client=admin_client,
            hco_namespace=ovs_daemonset.namespace,
            count=ovs_daemonset.instance.status.desiredNumberScheduled,
        )

    @pytest.mark.polarion("CNV-5531")
    def test_ovs_not_installed_annotations_disabled(
        self,
        admin_client,
        ovs_daemonset,
        hyperconverged_ovs_annotations_disabled,
        network_addons_config,
    ):
        wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
        wait_for_ovs_daemonset_deleted(ovs_daemonset=ovs_daemonset)
        wait_for_ovs_pods(
            admin_client=admin_client, hco_namespace=ovs_daemonset.namespace
        )

    @pytest.mark.polarion("CNV-5533")
    def test_ovs_not_installed_annotations_removed(
        self,
        admin_client,
        ovs_daemonset,
        hyperconverged_ovs_annotations_removed,
        network_addons_config,
    ):
        wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
        wait_for_ovs_daemonset_deleted(ovs_daemonset=ovs_daemonset)
        wait_for_ovs_pods(
            admin_client=admin_client, hco_namespace=ovs_daemonset.namespace
        )
