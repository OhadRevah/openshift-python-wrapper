# -*- coding: utf-8 -*-

"""
Clone tests
"""

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.utils import TimeoutSampler
from ocp_resources.volume_snapshot import VolumeSnapshot
from pytest_testconfig import config as py_config

import utilities.storage
from tests.storage import utils
from utilities.constants import TIMEOUT_10MIN
from utilities.infra import Images


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
    with utilities.storage.create_dv(
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
        {
            "dv_name": "dv-source",
            "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            "dv_size": "10Gi",
        },
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-2148")
def test_successful_vm_restart_with_cloned_dv(
    skip_upstream,
    namespace,
    data_volume_multi_storage_scope_function,
):
    with utilities.storage.create_dv(
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
            vm_dv.restart(timeout=300, wait=True)
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
                "cpu_threads": 2,
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
    with utilities.storage.create_dv(
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
    with utilities.storage.create_dv(
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
    with utilities.storage.create_dv(
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
            timeout=300,
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
