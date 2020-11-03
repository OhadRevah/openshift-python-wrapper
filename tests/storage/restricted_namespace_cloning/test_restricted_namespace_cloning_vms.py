"""
Restricted namespace cloning
"""

import logging

import pytest
from kubernetes.client.rest import ApiException
from resources.datavolume import DataVolume
from resources.service_account import ServiceAccount
from tests.storage.restricted_namespace_cloning.conftest import (
    DV_PARAMS,
    NAMESPACE_PARAMS,
)
from tests.storage.utils import (
    create_cluster_role,
    create_dv,
    create_role_binding,
    create_vm_and_verify_image_permission,
    set_permissions,
    storage_params,
)
from utilities.infra import Images
from utilities.storage import ErrorMsg
from utilities.virt import VirtualMachineForTests


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures("skip_when_no_unprivileged_client_available")


@pytest.fixture(scope="module")
def restricted_ns_service_account(dst_ns):
    with ServiceAccount(name="vm-service-account", namespace=dst_ns.name) as sa:
        yield sa


@pytest.fixture(scope="module")
def cluster_role_for_creating_pods():
    with create_cluster_role(
        name="pod-creator",
        api_groups=[""],
        verbs=["create"],
        permissions_to_resources=["pods"],
    ) as cluster_role_pod_creator:
        yield cluster_role_pod_creator


@pytest.fixture(scope="module")
def data_volume_clone_settings(
    namespace, dst_ns, data_volume_multi_storage_scope_module
):
    dv = DataVolume(
        name="dv",
        namespace=dst_ns.name,
        source="pvc",
        source_pvc=data_volume_multi_storage_scope_module.name,
        source_namespace=namespace.name,
        volume_mode=data_volume_multi_storage_scope_module.volume_mode,
        access_modes=data_volume_multi_storage_scope_module.access_modes,
        storage_class=data_volume_multi_storage_scope_module.storage_class,
        size=data_volume_multi_storage_scope_module.size,
        hostpath_node=data_volume_multi_storage_scope_module.hostpath_node,
    )
    return dv


@pytest.fixture()
def allow_unprivileged_client_to_manage_vms_on_dst_ns(
    dst_ns, api_group, unprivileged_user_username
):
    with create_role_binding(
        name="allow_unprivileged_client_to_run_vms_on_dst_ns",
        namespace=dst_ns.name,
        subjects_kind="User",
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
        role_ref_kind="ClusterRole",
        role_ref_name="kubevirt.io:admin",
    ) as role_binding_vm_admin_unprivileged_client:
        yield role_binding_vm_admin_unprivileged_client


@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_module", "namespace"),
    [
        pytest.param(
            DV_PARAMS, NAMESPACE_PARAMS, marks=pytest.mark.polarion("CNV-2826")
        ),
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_positive(
    namespace,
    dst_ns,
    restricted_ns_service_account,
    unprivileged_client,
    allow_unprivileged_client_to_manage_vms_on_dst_ns,
    data_volume_clone_settings,
):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role_bind_src",
        namespace=namespace.name,
        subjects_kind=restricted_ns_service_account.kind,
        subjects_name=restricted_ns_service_account.name,
        subjects_namespace=dst_ns.name,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=["*"],
            permissions_to_resources=["datavolumes", "datavolumes/source"],
            binding_name="role_bind_dst",
            namespace=dst_ns.name,
            subjects_kind=restricted_ns_service_account.kind,
            subjects_name=restricted_ns_service_account.name,
            subjects_namespace=dst_ns.name,
        ):
            dv_clone_dict = data_volume_clone_settings.to_dict()
            with VirtualMachineForTests(
                name="vm-for-test",
                namespace=dst_ns.name,
                service_accounts=[restricted_ns_service_account.name],
                client=unprivileged_client,
                memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
                data_volume_template={
                    "metadata": dv_clone_dict["metadata"],
                    "spec": dv_clone_dict["spec"],
                },
            ) as vm:
                vm.start(wait=True)


@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_module", "namespace"),
    [
        pytest.param(
            DV_PARAMS, NAMESPACE_PARAMS, marks=pytest.mark.polarion("CNV-2828")
        ),
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_grant_unprivileged_client_permissions_negative(
    namespace,
    dst_ns,
    restricted_ns_service_account,
    unprivileged_client,
    unprivileged_user_username,
    allow_unprivileged_client_to_manage_vms_on_dst_ns,
    data_volume_clone_settings,
    api_group,
):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=["*"],
        permissions_to_resources=["datavolumes/source"],
        binding_name="role_bind_src",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=["*"],
            permissions_to_resources=["datavolumes"],
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
                dv_clone_dict = data_volume_clone_settings.to_dict()
                with VirtualMachineForTests(
                    name="vm-for-test",
                    namespace=dst_ns.name,
                    service_accounts=[restricted_ns_service_account.name],
                    client=unprivileged_client,
                    memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
                    data_volume_template={
                        "metadata": dv_clone_dict["metadata"],
                        "spec": dv_clone_dict["spec"],
                    },
                ):
                    return


@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_module", "namespace"),
    [
        pytest.param(
            DV_PARAMS, NAMESPACE_PARAMS, marks=pytest.mark.polarion("CNV-2827")
        ),
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_restricted_ns_service_account_missing_cloning_permission_negative(
    namespace,
    dst_ns,
    restricted_ns_service_account,
    unprivileged_client,
    data_volume_clone_settings,
):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=["*"],
        permissions_to_resources=["datavolumes"],
        binding_name="role_bind_src",
        namespace=namespace.name,
        subjects_kind=restricted_ns_service_account.kind,
        subjects_name=restricted_ns_service_account.name,
        subjects_namespace=dst_ns.name,
    ):
        with set_permissions(
            role_name="datavolume-cluster-role-dst",
            verbs=["*"],
            permissions_to_resources=["datavolumes"],
            binding_name="role_bind_dst",
            namespace=dst_ns.name,
            subjects_kind=restricted_ns_service_account.kind,
            subjects_name=restricted_ns_service_account.name,
            subjects_namespace=dst_ns.name,
        ):
            with pytest.raises(
                ApiException,
                match=ErrorMsg.CANNOT_CREATE_RESOURCE,
            ):
                dv_clone_dict = data_volume_clone_settings.to_dict()
                with VirtualMachineForTests(
                    name="vm-for-test",
                    namespace=dst_ns.name,
                    service_accounts=[restricted_ns_service_account.name],
                    client=unprivileged_client,
                    memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
                    data_volume_template={
                        "metadata": dv_clone_dict["metadata"],
                        "spec": dv_clone_dict["spec"],
                    },
                ):
                    return


@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_module", "namespace"),
    [
        pytest.param(
            DV_PARAMS, NAMESPACE_PARAMS, marks=pytest.mark.polarion("CNV-2829")
        ),
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_permissions_for_pods_positive(
    namespace,
    dst_ns,
    restricted_ns_service_account,
    unprivileged_client,
    unprivileged_user_username,
    data_volume_clone_settings,
    cluster_role_for_creating_pods,
    allow_unprivileged_client_to_manage_vms_on_dst_ns,
):
    with create_role_binding(
        name="service-account-can-create-pods-on-src",
        namespace=namespace.name,
        subjects_kind=restricted_ns_service_account.kind,
        subjects_name=restricted_ns_service_account.name,
        role_ref_kind=cluster_role_for_creating_pods.kind,
        role_ref_name=cluster_role_for_creating_pods.name,
        subjects_namespace=dst_ns.name,
    ):
        with create_role_binding(
            name="service-account-can-create-pods-on-dst",
            namespace=dst_ns.name,
            subjects_kind=restricted_ns_service_account.kind,
            subjects_name=restricted_ns_service_account.name,
            role_ref_kind=cluster_role_for_creating_pods.kind,
            role_ref_name=cluster_role_for_creating_pods.name,
            subjects_namespace=dst_ns.name,
        ):
            dv_clone_dict = data_volume_clone_settings.to_dict()
            with VirtualMachineForTests(
                name="vm-for-test",
                namespace=dst_ns.name,
                service_accounts=[restricted_ns_service_account.name],
                client=unprivileged_client,
                memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
                data_volume_template={
                    "metadata": dv_clone_dict["metadata"],
                    "spec": dv_clone_dict["spec"],
                },
            ) as vm:
                vm.start(wait=True)


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
            (["datavolumes", "datavolumes/source"], ["*"]),
            (["datavolumes", "datavolumes/source"], ["*"]),
            marks=(pytest.mark.polarion("CNV-4034")),
        )
    ],
    indirect=["namespace", "data_volume_multi_storage_scope_module"],
)
def test_disk_image_after_create_vm_with_restricted_clone(
    skip_block_volumemode_scope_module,
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
                source_pvc=data_volume_multi_storage_scope_module.pvc.name,
                source_namespace=namespace.name,
                client=unprivileged_client,
                **storage_params(storage_class_matrix=storage_class_matrix__module__),
            ) as cdv:
                cdv.wait()
                create_vm_and_verify_image_permission(dv=cdv)
