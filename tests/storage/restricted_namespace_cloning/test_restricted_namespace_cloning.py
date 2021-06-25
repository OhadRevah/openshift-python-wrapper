"""
Restricted namespace cloning
"""

import logging

import pytest
from kubernetes.client.rest import ApiException

from tests.storage import utils
from tests.storage.constants import DV_PARAMS, NAMESPACE_PARAMS
from tests.storage.utils import set_permissions
from utilities.storage import ErrorMsg, create_dv


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures("skip_when_no_unprivileged_client_available")


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2688"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_same_namespace_negative(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
):
    storage_class = [*storage_class_matrix__module__][0]
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name="target-dv-cnv-2688",
            namespace=namespace.name,
            source="pvc",
            size=data_volume_multi_storage_scope_module.size,
            storage_class=storage_class,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
            source_pvc=data_volume_multi_storage_scope_module.pvc.name,
            source_namespace=namespace.name,
            client=unprivileged_client,
        ):
            return


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2688"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_same_namespace_positive(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
    unprivileged_user_username,
    api_group,
):
    storage_class = [*storage_class_matrix__module__][0]
    with set_permissions(
        role_name="datavolume-cluster-role",
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role-bind-data-volume",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        with create_dv(
            dv_name="target-dv",
            namespace=namespace.name,
            source="pvc",
            size=data_volume_multi_storage_scope_module.size,
            storage_class=storage_class,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
            source_pvc=data_volume_multi_storage_scope_module.pvc.name,
            source_namespace=namespace.name,
            client=unprivileged_client,
        ) as cdv:
            cdv.wait()
            with utils.create_vm_from_dv(dv=cdv):
                return


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2688"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_different_namespaces_negative(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
    dst_ns,
):
    storage_class = [*storage_class_matrix__module__][0]
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name="target-dv",
            namespace=dst_ns.name,
            source="pvc",
            size=data_volume_multi_storage_scope_module.size,
            storage_class=storage_class,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
            source_pvc=data_volume_multi_storage_scope_module.pvc.name,
            source_namespace=namespace.name,
            client=unprivileged_client,
        ):
            return


@pytest.mark.parametrize(
    (
        "namespace",
        "data_volume_multi_storage_scope_module",
        "permissions_src",
        "permissions_dst",
    ),
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes", "datavolumes/source"], ["create", "delete"]),
            (
                ["datavolumes", "datavolumes/source"],
                ["create", "delete", "list", "get"],
            ),
            marks=(pytest.mark.polarion("CNV-2689")),
            id="src_ns: dv and dv/src, verbs: create, delete. dst: dv and dv/src, verbs: create, delete, list, get.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes", "datavolumes/source"], ["*"]),
            (["datavolumes", "datavolumes/source"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2692")),
            id="src_ns: dv and dv/src, verbs: *. dst: dv and dv/src, verbs: *.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes", "datavolumes/source"], ["*"]),
            (["datavolumes"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2805")),
            id="src_ns: dv and dv/src, verbs: *. dst: dv, verbs: *.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes", "datavolumes/source"], ["create", "delete"]),
            (["datavolumes"], ["create", "delete", "list", "get"]),
            marks=(pytest.mark.polarion("CNV-2808")),
            id="src_ns: dv and dv/src, verbs: create, delete. dst: dv, verbs: create, delete, list, get.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes/source"], ["create"]),
            (["datavolumes"], ["create", "delete", "list", "get"]),
            marks=(pytest.mark.polarion("CNV-2971")),
            id="src_ns: dv/src, verbs: create. dst: dv, verbs: create, delete, list, get.",
        ),
    ],
    indirect=["namespace", "data_volume_multi_storage_scope_module"],
)
def test_user_permissions_positive(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    dst_ns,
    unprivileged_client,
    permissions_src,
    permissions_dst,
    unprivileged_user_username,
    api_group,
):
    storage_class = [*storage_class_matrix__module__][0]
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=permissions_src[1],
        permissions_to_resources=permissions_src[0],
        binding_name="role_bind_src",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=permissions_dst[1],
            permissions_to_resources=permissions_dst[0],
            binding_name="role_bind_dst",
            namespace=dst_ns.name,
            subjects_kind="User",
            subjects_name=unprivileged_user_username,
            subjects_api_group=api_group,
        ):
            with create_dv(
                dv_name="target-dv",
                namespace=dst_ns.name,
                source="pvc",
                size=data_volume_multi_storage_scope_module.size,
                storage_class=storage_class,
                volume_mode=storage_class_matrix__module__[storage_class][
                    "volume_mode"
                ],
                source_pvc=data_volume_multi_storage_scope_module.pvc.name,
                source_namespace=namespace.name,
                client=unprivileged_client,
            ) as cdv:
                cdv.wait()
                with utils.create_vm_from_dv(dv=cdv):
                    return


@pytest.mark.parametrize(
    (
        "namespace",
        "data_volume_multi_storage_scope_module",
        "permissions_src",
        "permissions_dst",
    ),
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes"], ["create", "delete"]),
            (["datavolumes"], ["create", "delete"]),
            marks=(pytest.mark.polarion("CNV-2793")),
            id="src_ns: dv, verbs: create, delete. dst: dv, verbs: create, delete.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes"], ["list", "get"]),
            (["datavolumes", "datavolumes/source"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2691")),
            id="src_ns: dv, verbs: list, get. dst: dv and dv/src, verbs: *.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            (["datavolumes"], ["*"]),
            (["datavolumes"], ["*"]),
            marks=(pytest.mark.polarion("CNV-2804")),
            id="src_ns: dv, verbs: *. dst: dv, verbs: *.",
        ),
    ],
    indirect=["namespace", "data_volume_multi_storage_scope_module"],
)
def test_user_permissions_negative(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    dst_ns,
    unprivileged_client,
    permissions_src,
    permissions_dst,
    unprivileged_user_username,
    api_group,
):
    storage_class = [*storage_class_matrix__module__][0]
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=permissions_src[1],
        permissions_to_resources=permissions_src[0],
        binding_name="role_bind_src",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=permissions_dst[1],
            permissions_to_resources=permissions_dst[0],
            binding_name="role_bind_dst",
            namespace=dst_ns.name,
            subjects_kind="User",
            subjects_name=unprivileged_user_username,
            subjects_api_group=api_group,
        ):
            with pytest.raises(
                ApiException,
                match=ErrorMsg.CANNOT_CREATE_RESOURCE,
            ):
                with create_dv(
                    dv_name="target-dv",
                    namespace=dst_ns.name,
                    source="pvc",
                    size=data_volume_multi_storage_scope_module.size,
                    storage_class=storage_class,
                    volume_mode=storage_class_matrix__module__[storage_class][
                        "volume_mode"
                    ],
                    source_pvc=data_volume_multi_storage_scope_module.pvc.name,
                    source_namespace=namespace.name,
                    client=unprivileged_client,
                ):
                    return


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2688"),
        ),
    ],
    indirect=True,
)
def test_user_permissions_only_for_dst_ns_negative(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    dst_ns,
    unprivileged_client,
    unprivileged_user_username,
    api_group,
):
    storage_class = [*storage_class_matrix__module__][0]
    with set_permissions(
        role_name="datavolume-cluster-role-dst",
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role_bind_dst",
        namespace=dst_ns.name,
        subjects_kind="User",
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        with pytest.raises(
            ApiException,
            match=ErrorMsg.CANNOT_CREATE_RESOURCE,
        ):
            with create_dv(
                dv_name="target-dv",
                namespace=dst_ns.name,
                source="pvc",
                size=data_volume_multi_storage_scope_module.size,
                storage_class=storage_class,
                volume_mode=storage_class_matrix__module__[storage_class][
                    "volume_mode"
                ],
                source_pvc=data_volume_multi_storage_scope_module.pvc.name,
                source_namespace=namespace.name,
                client=unprivileged_client,
            ):
                return
