import logging

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.pod import Pod
from ocp_resources.replicaset import ReplicaSet
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.utils import TimeoutSampler
from pytest_testconfig import config as py_config

from tests.storage import utils as storage_utils
from utilities import storage as utils
from utilities.constants import TIMEOUT_10MIN
from utilities.infra import Images
from utilities.storage import get_images_server_url


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)
CDI_LABEL = "cdi.kubevirt.io"


def verify_label(cdi_resources):
    bad_pods = []
    for rcs in cdi_resources:
        if rcs.name.startswith("cdi-operator"):
            continue
        if CDI_LABEL not in rcs.instance.metadata.labels.keys():
            bad_pods.append(rcs.name)
    assert not bad_pods, " ".join(bad_pods)


@pytest.mark.parametrize(
    "cdi_resources",
    [
        pytest.param(
            {"resource": Pod},
            marks=(pytest.mark.polarion("CNV-1034")),
            id="cdi-pods",
        ),
        pytest.param(
            {"resource": ServiceAccount},
            marks=(pytest.mark.polarion("CNV-3478")),
            id="cdi-service-accounts",
        ),
        pytest.param(
            {"resource": Service},
            marks=(pytest.mark.polarion("CNV-3479")),
            id="cdi-service",
        ),
        pytest.param(
            {"resource": Deployment},
            marks=(pytest.mark.polarion("CNV-3480")),
            id="cdi-deployment",
        ),
        pytest.param(
            {"resource": ReplicaSet},
            marks=(pytest.mark.polarion("CNV-3481")),
            id="cdi-replicatset",
        ),
        pytest.param(
            {"resource": CustomResourceDefinition},
            marks=(pytest.mark.polarion("CNV-3482")),
            id="cdi-crd",
        ),
        pytest.param(
            {"resource": Role},
            marks=(pytest.mark.polarion("CNV-3483")),
            id="cdi-role",
        ),
        pytest.param(
            {"resource": RoleBinding},
            marks=(pytest.mark.polarion("CNV-3484")),
            id="cdi-role-binding",
        ),
        pytest.param(
            {"resource": ClusterRole},
            marks=(pytest.mark.polarion("CNV-3485")),
            id="cdi-cluster-role",
        ),
        pytest.param(
            {"resource": ClusterRoleBinding},
            marks=(pytest.mark.polarion("CNV-3486")),
            id="cdi-cluster-role-binding",
        ),
    ],
    indirect=True,
)
def test_verify_pod_cdi_label(cdi_resources):
    verify_label(cdi_resources=cdi_resources)


def _pods_list(dyn_client, pod_name, storage_ns_name):
    pods = list(Pod.get(dyn_client=dyn_client, namespace=storage_ns_name))
    return [pod for pod in pods if pod_name in pod.name]


def is_cdi_worker_pod(dyn_client, pod_name, storage_ns_name):
    """pod_name can also be partial pod name"""
    LOGGER.info("waiting for worker pod")
    sampler = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=_pods_list,
        dyn_client=dyn_client,
        pod_name=pod_name,
        storage_ns_name=storage_ns_name,
    )
    for sample in sampler:
        if [pod for pod in sample if CDI_LABEL in pod.labels.keys()]:
            break


@pytest.mark.polarion("CNV-3475")
def test_importer_pod_cdi_label(skip_upstream, admin_client, namespace):
    # verify "cdi.kubevirt.io" label is included in importer pod
    with storage_utils.import_image_to_dv(
        dv_name="cnv-3475",
        images_https_server_name=get_images_server_url(schema="https"),
        volume_mode=py_config["default_volume_mode"],
        access_mode=py_config["default_access_mode"],
        storage_ns_name=namespace.name,
    ):
        is_cdi_worker_pod(
            dyn_client=admin_client,
            pod_name="importer",
            storage_ns_name=namespace.name,
        )


@pytest.mark.polarion("CNV-3474")
def test_uploader_pod_cdi_label(
    admin_client, storage_class_matrix__module__, namespace, unprivileged_client
):
    """
    Verify "cdi.kubevirt.io" label is included in uploader pod
    """
    storage_class = [*storage_class_matrix__module__][0]
    with storage_utils.upload_image_to_dv(
        dv_name="cnv-3474",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        storage_ns_name=namespace.name,
        client=unprivileged_client,
    ):
        is_cdi_worker_pod(
            dyn_client=admin_client,
            pod_name="cdi-upload",
            storage_ns_name=namespace.name,
        )


@pytest.mark.polarion("CNV-3476")
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
        ),
    ],
    indirect=True,
)
def test_cloner_pods_cdi_label(
    skip_upstream,
    admin_client,
    namespace,
    data_volume_multi_storage_scope_function,
):
    # verify "cdi.kubevirt.io" label is included in cloning pods
    if storage_utils.smart_clone_supported_by_sc(
        sc=data_volume_multi_storage_scope_function.storage_class, client=admin_client
    ):
        pytest.skip(
            f"Storage Class {data_volume_multi_storage_scope_function.storage_class} supports smart cloning; "
            "CDI Worker pods will not be created for this operation, skipping test"
        )
    with utils.create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_multi_storage_scope_function.namespace,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
        access_modes=data_volume_multi_storage_scope_function.access_modes,
    ) as cdv:
        cdv.wait_for_status(
            status=DataVolume.Status.CLONE_IN_PROGRESS, timeout=TIMEOUT_10MIN
        )
        is_cdi_worker_pod(
            dyn_client=admin_client,
            pod_name="cdi-upload-dv-target",
            storage_ns_name=cdv.namespace,
        )
        is_cdi_worker_pod(
            dyn_client=admin_client,
            pod_name="-source-pod",
            storage_ns_name=cdv.namespace,
        )