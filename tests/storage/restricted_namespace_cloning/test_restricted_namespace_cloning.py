"""
Restricted namespace cloning
"""

import logging
from contextlib import contextmanager

import pytest
from kubernetes.client.rest import ApiException
from pytest_testconfig import config as py_config
from resources.namespace import Namespace
from tests.storage import utils
from tests.storage.utils import create_cluster_role, create_role_binding
from utilities.infra import Images, get_images_external_http_server
from utilities.storage import create_dv


LOGGER = logging.getLogger(__name__)
UNPRIVILEGED_USER = "unprivileged-user"


@contextmanager
def set_permissions(
    role_name, verbs, permissions_to_resources, binding_name, namespace, subjects_name
):
    with create_cluster_role(
        name=role_name,
        api_groups=["cdi.kubevirt.io"],
        permissions_to_resources=permissions_to_resources,
        verbs=verbs,
    ) as cluster_role:
        with create_role_binding(
            name=binding_name,
            namespace=namespace,
            subjects_kind="User",
            subjects_name=subjects_name,
            role_ref_kind=cluster_role.kind,
            role_ref_name=cluster_role.name,
        ) as role_binding:
            yield [cluster_role, role_binding]


@pytest.fixture(scope="module")
def data_volume(storage_ns):
    with create_dv(
        dv_name="source-dv",
        namespace=storage_ns.name,
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size="500Mi",
    ) as dv:
        dv.wait()
        yield dv


@pytest.fixture(scope="module")
def create_ns():
    with Namespace(name="destination-namespace") as ns:
        ns.wait_for_status(Namespace.Status.ACTIVE, timeout=120)
        yield ns


@pytest.mark.polarion("CNV-2688")
def test_unprivileged_user_clone_same_namespace_negative(
    storage_ns, data_volume, unprivileged_client
):
    with pytest.raises(
        ApiException,
        match=r".*cannot create resource.*|.*has insufficient permissions in clone source namespace.*",
    ):
        with create_dv(
            dv_name="target-dv-cnv-2688",
            namespace=storage_ns.name,
            source="pvc",
            size="500Mi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
            source_pvc=data_volume.pvc.name,
            source_namespace=storage_ns.name,
            client=unprivileged_client,
        ):
            return


@pytest.mark.polarion("CNV-2768")
def test_unprivileged_user_clone_same_namespace_positive(
    storage_ns, data_volume, unprivileged_client
):
    with set_permissions(
        role_name="datavolume-cluster-role",
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role-bind-data-volume",
        namespace=storage_ns.name,
        subjects_name=UNPRIVILEGED_USER,
    ):
        with create_dv(
            dv_name="target-dv",
            namespace=storage_ns.name,
            source="pvc",
            size="500Mi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
            source_pvc=data_volume.pvc.name,
            source_namespace=storage_ns.name,
            client=unprivileged_client,
        ) as cdv:
            cdv.wait()
            with utils.create_vm_from_dv(cdv):
                return


@pytest.mark.parametrize(
    ("permissions_src", "permissions_dst"),
    [
        pytest.param(
            (["datavolumes", "datavolumes/source"], ["create", "delete"]),
            (
                ["datavolumes", "datavolumes/source"],
                ["create", "delete", "list", "get"],
            ),
            marks=(pytest.mark.polarion("CNV-2689")),
            id="src_ns: dv and dv/src, verbs: create, delete. dst: dv and dv/src, verbs: create, delete, list, get.",
        ),
        pytest.param(
            (["datavolumes", "datavolumes/source"], ["*"]),
            (["datavolumes", "datavolumes/source"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2692")),
            id="src_ns: dv and dv/src, verbs: *. dst: dv and dv/src, verbs: *.",
        ),
        pytest.param(
            (["datavolumes", "datavolumes/source"], ["*"]),
            (["datavolumes"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2805")),
            id="src_ns: dv and dv/src, verbs: *. dst: dv, verbs: *.",
        ),
        pytest.param(
            (["datavolumes", "datavolumes/source"], ["create", "delete"]),
            (["datavolumes"], ["create", "delete", "list", "get"]),
            marks=(pytest.mark.polarion("CNV-2808")),
            id="src_ns: dv and dv/src, verbs: create, delete. dst: dv, verbs: create, delete, list, get.",
        ),
        pytest.param(
            (["datavolumes/source"], ["create"]),
            (["datavolumes"], ["create", "delete", "list", "get"]),
            marks=(pytest.mark.polarion("CNV-2971")),
            id="src_ns: dv/src, verbs: create. dst: dv, verbs: create, delete, list, get.",
        ),
    ],
)
def test_user_permissions_positive(
    storage_ns,
    data_volume,
    create_ns,
    unprivileged_client,
    permissions_src,
    permissions_dst,
):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=permissions_src[1],
        permissions_to_resources=permissions_src[0],
        binding_name="role_bind_src",
        namespace=storage_ns.name,
        subjects_name=UNPRIVILEGED_USER,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=permissions_dst[1],
            permissions_to_resources=permissions_dst[0],
            binding_name="role_bind_dst",
            namespace=create_ns.name,
            subjects_name=UNPRIVILEGED_USER,
        ):
            with create_dv(
                dv_name="target-dv",
                namespace=create_ns.name,
                source="pvc",
                size="500Mi",
                storage_class=py_config["default_storage_class"],
                volume_mode=py_config["default_volume_mode"],
                source_pvc=data_volume.pvc.name,
                source_namespace=storage_ns.name,
                client=unprivileged_client,
            ) as cdv:
                cdv.wait()
                with utils.create_vm_from_dv(cdv):
                    return


@pytest.mark.parametrize(
    ("permissions_src", "permissions_dst"),
    [
        pytest.param(
            (["datavolumes"], ["create", "delete"]),
            (["datavolumes"], ["create", "delete"]),
            marks=(pytest.mark.polarion("CNV-2793")),
            id="src_ns: dv, verbs: create, delete. dst: dv, verbs: create, delete.",
        ),
        pytest.param(
            (["datavolumes"], ["list", "get"]),
            (["datavolumes", "datavolumes/source"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2691")),
            id="src_ns: dv, verbs: list, get. dst: dv and dv/src, verbs: *.",
        ),
        pytest.param(
            (["datavolumes"], ["*"]),
            (["datavolumes"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2804")),
            id="src_ns: dv, verbs: *. dst: dv, verbs: *.",
        ),
    ],
)
def test_user_permissions_negative(
    storage_ns,
    data_volume,
    create_ns,
    unprivileged_client,
    permissions_src,
    permissions_dst,
):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=permissions_src[1],
        permissions_to_resources=permissions_src[0],
        binding_name="role_bind_src",
        namespace=storage_ns.name,
        subjects_name=UNPRIVILEGED_USER,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=permissions_dst[1],
            permissions_to_resources=permissions_dst[0],
            binding_name="role_bind_dst",
            namespace=create_ns.name,
            subjects_name=UNPRIVILEGED_USER,
        ):
            with pytest.raises(
                ApiException,
                match=r".*cannot create resource.*|.*has insufficient permissions in clone source namespace.*",
            ):
                with create_dv(
                    dv_name="target-dv",
                    namespace=create_ns.name,
                    source="pvc",
                    size="500Mi",
                    storage_class=py_config["default_storage_class"],
                    volume_mode=py_config["default_volume_mode"],
                    source_pvc=data_volume.pvc.name,
                    source_namespace=storage_ns.name,
                    client=unprivileged_client,
                ):
                    return
