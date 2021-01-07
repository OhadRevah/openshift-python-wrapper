import logging

import pytest
from resources.daemonset import DaemonSet
from resources.pod import Pod
from resources.resource import ResourceEditor
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.infra import get_pod_by_name_prefix


LOGGER = logging.getLogger()
OVS_DS_NAME = "ovs-cni-amd64"
DEPLOY_OVS = "deployOVS"


def replace_annotations(hyperconverged_resource, annotations):
    metadata = {
        "metadata": {
            "annotations": annotations,
            "name": hyperconverged_resource.name,
            "resourceVersion": hyperconverged_resource.instance.metadata.resourceVersion,
        },
        "kind": hyperconverged_resource.kind,
        "apiVersion": hyperconverged_resource.api_version,
    }
    hyperconverged_resource.api().replace(
        metadata, namespace=hyperconverged_resource.namespace
    )


def wait_for_ovs_daemonset_deleted(ovs_daemonset):
    samples = TimeoutSampler(timeout=60, sleep=1, func=lambda: ovs_daemonset.exists)
    try:
        for sample in samples:
            if not sample:
                return True

    except TimeoutExpiredError:
        LOGGER.error("OVD daemonset exists after opt-out")
        raise


def wait_for_ovs_pods(admin_client, hco_namespace, count=0):
    samples = TimeoutSampler(
        timeout=60,
        sleep=1,
        func=ovs_pods,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    num_of_pods = None
    try:
        for sample in samples:
            num_of_pods = len(sample) if sample is not None else 0
            if not sample and count == 0:
                return True

            if num_of_pods == count:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"Found {num_of_pods} OVS PODs, expected: {count}")
        raise


def wait_for_ovs_status(network_addons_config, status=True):
    samples = TimeoutSampler(
        timeout=60,
        sleep=1,
        func=lambda: network_addons_config.instance.to_dict()["spec"].get("ovs"),
    )

    try:
        for sample in samples:
            if sample is not None and status:
                return True

            if sample is None and not status:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"OVS should be {'opt-in' if status else 'opt-out'}")
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
    replace_annotations(
        hyperconverged_resource=hyperconverged_resource, annotations=annotations
    )
    yield
    replace_annotations(
        hyperconverged_resource=hyperconverged_resource, annotations=origin_annotations
    )
    wait_for_ovs_status(network_addons_config=network_addons_config, status=True)
    ovs_daemonset.wait_until_deployed()


@pytest.fixture(scope="class")
def ovs_daemonset(admin_client, hco_namespace):
    ovs_ds = list(
        DaemonSet.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            field_selector=f"metadata.name=={OVS_DS_NAME}",
        )
    )
    return ovs_ds[0] if ovs_ds else None


def ovs_pods(admin_client, hco_namespace):
    pods = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=OVS_DS_NAME,
        namespace=hco_namespace,
        get_all=True,
    )
    return (
        [pod for pod in pods if pod.instance.status.phase == Pod.Status.RUNNING]
        if pods
        else pods
    )


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
