import logging

import pytest
from pytest_testconfig import config as py_config
from resources.cluster_role import ClusterRole
from resources.cluster_role_binding import ClusterRoleBinding
from resources.custom_resource_definition import CustomResourceDefinition
from resources.datavolume import DataVolume
from resources.deployment import Deployment
from resources.pod import Pod
from resources.replicaset import ReplicaSet
from resources.role import Role
from resources.role_binding import RoleBinding
from resources.service import Service
from resources.service_account import ServiceAccount
from resources.utils import TimeoutSampler
from tests.storage import utils as storage_utils
from utilities import storage as utils
from utilities.infra import Images
from utilities.storage import get_images_https_server


LOGGER = logging.getLogger(__name__)


def verify_label(cdi_resources):
    bad_pods = []
    for rcs in cdi_resources:
        if rcs.name.startswith("cdi-operator"):
            continue
        if "cdi.kubevirt.io" not in rcs.instance.metadata.labels.keys():
            bad_pods.append(rcs.name)
    assert not bad_pods, " ".join(bad_pods)


@pytest.mark.parametrize(
    "cdi_resources",
    [
        pytest.param(
            {"resource": Pod}, marks=(pytest.mark.polarion("CNV-1034")), id="cdi-pods",
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
            {"resource": Role}, marks=(pytest.mark.polarion("CNV-3483")), id="cdi-role",
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


def _resource_list(default_client, pod_prefix, storage_ns_name):
    pods = list(Pod.get(dyn_client=default_client, namespace=storage_ns_name))
    return [pod for pod in pods if pod.name.startswith(pod_prefix)]


def get_cdi_worker_pods(default_client, pod_prefix, storage_ns_name):
    LOGGER.info("waiting for worker pod")
    sampler = TimeoutSampler(
        timeout=30,
        sleep=1,
        func=_resource_list,
        default_client=default_client,
        pod_prefix=pod_prefix,
        storage_ns_name=storage_ns_name,
    )
    for sample in sampler:
        if [pod for pod in sample if "cdi.kubevirt.io" in pod.labels.keys()]:
            break


@pytest.mark.polarion("CNV-3475")
def test_importer_pod_cdi_label(skip_upstream, default_client, namespace):
    # verify "cdi.kubevirt.io" label is included in importer pod
    with storage_utils.import_image_to_dv(
        dv_name="cnv-3475",
        images_https_server_name=get_images_https_server(),
        volume_mode=py_config["default_volume_mode"],
        storage_ns_name=namespace.name,
    ):
        get_cdi_worker_pods(
            default_client, pod_prefix="importer", storage_ns_name=namespace.name
        )


@pytest.mark.polarion("CNV-3474")
def test_uploader_pod_cdi_label(
    default_client, storage_class_matrix__module__, namespace
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
    ):
        get_cdi_worker_pods(
            default_client, pod_prefix="cdi-upload", storage_ns_name=namespace.name
        )


@pytest.mark.polarion("CNV-3476")
def test_cloner_pods_cdi_label(
    skip_upstream, default_client, namespace, https_config_map
):
    # verify "cdi.kubevirt.io" label is included in cloning pods
    url = storage_utils.get_file_url_https_server(
        images_https_server=get_images_https_server(),
        file_name=Images.Cirros.QCOW2_IMG,
    )
    with utils.create_dv(
        source="http",
        dv_name="dv-source",
        namespace=namespace.name,
        url=url,
        cert_configmap=https_config_map.name,
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait(timeout=300)
        with utils.create_dv(
            source="pvc",
            dv_name="dv-target",
            namespace=dv.namespace,
            size="10Gi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
        ) as dv1:
            dv1.wait_for_status(status=DataVolume.Status.CLONE_IN_PROGRESS, timeout=600)
            get_cdi_worker_pods(
                default_client,
                pod_prefix="cdi-clone-source-dv",
                storage_ns_name=dv.namespace,
            )
            get_cdi_worker_pods(
                default_client,
                pod_prefix="cdi-upload-dv-target",
                storage_ns_name=dv.namespace,
            )
