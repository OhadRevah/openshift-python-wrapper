import pytest

from utilities.constants import ALL_CNV_DAEMONSETS
from utilities.infra import get_daemonset_by_name, get_daemonsets


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture()
def cnv_daemonset_by_name(
    admin_client,
    hco_namespace,
    cnv_daemonset_matrix__function__,
):
    return get_daemonset_by_name(
        admin_client=admin_client,
        namespace_name=hco_namespace.name,
        daemonset_name=cnv_daemonset_matrix__function__,
    )


@pytest.fixture(scope="module")
def cnv_daemonset_names(admin_client, hco_namespace):
    return [
        daemonset.name
        for daemonset in get_daemonsets(
            admin_client=admin_client, namespace=hco_namespace.name
        )
    ]


@pytest.mark.polarion("CNV-8509")
def test_no_new_cnv_daemonset_added(cnv_daemonset_names):
    """
    Since cnv deployments image validations are done via polarion parameterization, this test has been added
    to catch any new cnv deployments that is not part of cnv_deployment_matrix
    """
    assert sorted(cnv_daemonset_names) == sorted(
        ALL_CNV_DAEMONSETS
    ), f"New cnv daemonsets found: {set(cnv_daemonset_names)-set(ALL_CNV_DAEMONSETS)}"


@pytest.mark.polarion("CNV-8378")
def test_cnv_daemonset_sno_one_scheduled(
    skip_if_not_sno_cluster, cnv_daemonset_by_name
):
    daemonset_name = cnv_daemonset_by_name.name
    daemonset_instance = cnv_daemonset_by_name.instance
    current_scheduled = daemonset_instance.status.currentNumberScheduled
    desired_scheduled = daemonset_instance.status.desiredNumberScheduled
    num_available = daemonset_instance.status.numberAvailable
    num_ready = daemonset_instance.status.numberReady
    updated_scheduled = daemonset_instance.status.updatedNumberScheduled
    base_error_message = f"For daemonset: {daemonset_name}, expected: 1, "
    assert (
        current_scheduled == 1
    ), f"{base_error_message} status.currentNumberScheduled: {current_scheduled}"
    assert (
        desired_scheduled == 1
    ), f"{base_error_message} status.desiredNumberScheduled: {desired_scheduled}"
    assert (
        num_available == 1
    ), f"{base_error_message} status.num_available:{num_available}"
    assert num_ready == 1, f"{base_error_message} status.num_ready:{num_ready}"
    assert (
        updated_scheduled == 1
    ), f"{base_error_message} status.updated_scheduled:{updated_scheduled}"
