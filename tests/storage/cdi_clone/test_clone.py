# -*- coding: utf-8 -*-

"""
Clone tests
"""

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutSampler
from ocp_resources.volume_snapshot import VolumeSnapshot
from pytest_testconfig import config as py_config

from tests.storage import utils
from utilities.constants import OS_FLAVOR_CIRROS, TIMEOUT_5MIN, TIMEOUT_10MIN
from utilities.infra import Images
from utilities.storage import (
    create_dv,
    data_volume_template_dict,
    get_images_server_url,
    overhead_size_for_dv,
)
from utilities.virt import VirtualMachineForTests, running_vm


WINDOWS_CLONE_TIMEOUT = 40 * 60


def verify_source_pvc_of_volume_snapshot(source_pvc_name, snapshot):
    for sample in TimeoutSampler(
        wait_timeout=20,
        sleep=1,
        func=lambda: snapshot.exists
        and snapshot.instance["spec"]["source"]["persistentVolumeClaimName"]
        == source_pvc_name,
    ):
        if sample:
            break


def create_vm_from_clone_dv_template(
    vm_name, dv_name, namespace_name, source_dv, client, volume_mode, size=None
):
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        os_flavor=OS_FLAVOR_CIRROS,
        client=client,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_dict(
            target_dv_name=dv_name,
            target_dv_namespace=namespace_name,
            source_dv=source_dv,
            volume_mode=volume_mode,
            size=size,
        ),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False)
        utils.check_disk_count_in_vm(vm=vm)


@pytest.fixture()
def ceph_rbd_data_volume(request, namespace):
    with create_dv(
        source="http",
        dv_name="ceph-rbd-dv",
        namespace=namespace.name,
        url=f"{get_images_server_url(schema='http')}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        storage_class=StorageClass.Types.CEPH_RBD,
        volume_mode=request.param["volume_mode"],
        access_modes=DataVolume.AccessMode.RWO,
    ) as dv:
        yield dv


@pytest.mark.tier3
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN19_IMG}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-1892")),
        ),
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3409")),
        ),
    ],
    indirect=True,
)
def test_successful_clone_of_large_image(
    skip_upstream,
    admin_client,
    namespace,
    data_volume_multi_storage_scope_function,
):
    conditions = [
        DataVolume.Condition.Type.BOUND,
        DataVolume.Condition.Type.RUNNING,
        DataVolume.Condition.Type.READY,
    ]
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
        access_modes=data_volume_multi_storage_scope_function.access_modes,
    ) as cdv:
        if utils.smart_clone_supported_by_sc(sc=cdv.storage_class, client=admin_client):
            # Smart clone via snapshots does not hit this condition; no workers are spawned
            conditions.remove(DataVolume.Condition.Type.RUNNING)
        for condition in conditions:
            cdv.wait_for_condition(
                condition=condition,
                status=DataVolume.Condition.Status.TRUE,
                timeout=WINDOWS_CLONE_TIMEOUT,
            )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "10Gi",
            },
            marks=(pytest.mark.polarion("CNV-2148"), pytest.mark.post_upgrade()),
        ),
    ],
    indirect=True,
)
def test_successful_vm_restart_with_cloned_dv(
    skip_upstream,
    namespace,
    data_volume_multi_storage_scope_function,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
        access_modes=data_volume_multi_storage_scope_function.access_modes,
    ) as cdv:
        cdv.wait(timeout=TIMEOUT_10MIN)
        with utils.create_vm_from_dv(dv=cdv) as vm_dv:
            vm_dv.restart(timeout=TIMEOUT_5MIN, wait=True)
            running_vm(vm=vm_dv, wait_for_interfaces=False)
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.tier3
@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_function", "vm_params"),
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "source": "http",
                "image": f"{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": f"vm-win-{py_config['latest_windows_os_dict']['os_version']}",
                "template_labels": py_config["latest_windows_os_dict"][
                    "template_labels"
                ],
                "os_version": py_config["latest_windows_os_dict"]["os_version"],
                "username": py_config["windows_username"],
                "password": py_config["windows_password"],
                "ssh": True,
            },
            marks=pytest.mark.polarion("CNV-3638"),
        ),
    ],
    indirect=["data_volume_multi_storage_scope_function"],
)
def test_successful_vm_from_cloned_dv_windows(
    skip_upstream,
    unprivileged_client,
    network_configuration,
    cloud_init_data,
    data_volume_multi_storage_scope_function,
    vm_params,
    namespace,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_multi_storage_scope_function.namespace,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
        access_modes=data_volume_multi_storage_scope_function.access_modes,
    ) as cdv:
        cdv.wait(timeout=WINDOWS_CLONE_TIMEOUT)
        assert cdv.pvc.bound()
        utils.create_windows_vm_validate_guest_agent_info(
            cloud_init_data=cloud_init_data,
            dv=cdv,
            namespace=namespace,
            network_configuration=network_configuration,
            unprivileged_client=unprivileged_client,
            vm_params=vm_params,
        )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "1Gi",
            },
            marks=pytest.mark.polarion("CNV-4035"),
        )
    ],
    indirect=True,
)
def test_disk_image_after_clone(
    skip_block_volumemode_scope_function,
    namespace,
    data_volume_multi_storage_scope_function,
    unprivileged_client,
):
    with create_dv(
        source="pvc",
        dv_name="dv-cnv-4035",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        client=unprivileged_client,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
        access_modes=data_volume_multi_storage_scope_function.access_modes,
    ) as cdv:
        cdv.wait()
        utils.create_vm_and_verify_image_permission(dv=cdv)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3545")),
        ),
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3552"), pytest.mark.tier3()),
        ),
    ],
    indirect=True,
)
def test_successful_snapshot_clone(
    skip_upstream,
    skip_smart_clone_not_supported_by_sc,
    namespace,
    data_volume_multi_storage_scope_function,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
        access_modes=data_volume_multi_storage_scope_function.access_modes,
    ) as cdv:
        cdv.wait_for_status(
            status=DataVolume.Status.SNAPSHOT_FOR_SMART_CLONE_IN_PROGRESS,
            timeout=TIMEOUT_5MIN,
        )
        snapshot = VolumeSnapshot(name=cdv.name, namespace=namespace.name)
        verify_source_pvc_of_volume_snapshot(
            source_pvc_name=data_volume_multi_storage_scope_function.pvc.name,
            snapshot=snapshot,
        )
        cdv.wait()
        if "win" not in data_volume_multi_storage_scope_function.url.split("/")[-1]:
            with utils.create_vm_from_dv(dv=cdv) as vm_dv:
                utils.check_disk_count_in_vm(vm=vm_dv)
        assert (
            cdv.pvc.instance.metadata.annotations.get("k8s.io/SmartCloneRequest")
            == "true"
        ), "Smart clone annotation does not exist on target PVC"
        snapshot.wait_deleted()


@pytest.mark.parametrize(
    "ceph_rbd_data_volume",
    [
        pytest.param(
            {
                "volume_mode": DataVolume.VolumeMode.FILE,
            },
            marks=(pytest.mark.polarion("CNV-5607")),
        ),
    ],
    indirect=True,
)
def test_clone_from_fs_to_block_using_dv_template(
    namespace, unprivileged_client, ceph_rbd_data_volume
):
    create_vm_from_clone_dv_template(
        vm_name="vm-5607",
        dv_name="dv-5607",
        namespace_name=namespace.name,
        source_dv=ceph_rbd_data_volume,
        client=unprivileged_client,
        volume_mode=DataVolume.VolumeMode.BLOCK,
    )


@pytest.mark.parametrize(
    "ceph_rbd_data_volume",
    [
        pytest.param(
            {
                "volume_mode": DataVolume.VolumeMode.BLOCK,
            },
            marks=(pytest.mark.polarion("CNV-5608")),
        ),
    ],
    indirect=True,
)
def test_clone_from_block_to_fs_using_dv_template(
    namespace,
    unprivileged_client,
    ceph_rbd_data_volume,
    default_fs_overhead,
):
    create_vm_from_clone_dv_template(
        vm_name="vm-5608",
        dv_name="dv-5608",
        namespace_name=namespace.name,
        source_dv=ceph_rbd_data_volume,
        client=unprivileged_client,
        volume_mode=DataVolume.VolumeMode.FILE,
        # add fs overhead and round up the result
        size=overhead_size_for_dv(
            image_size=int(ceph_rbd_data_volume.size[:-2]),
            overhead_value=default_fs_overhead,
        ),
    )
