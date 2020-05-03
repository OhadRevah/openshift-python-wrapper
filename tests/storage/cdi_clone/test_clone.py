# -*- coding: utf-8 -*-

"""
Clone tests
"""

import pytest
import utilities.storage
from pytest_testconfig import config as py_config
from tests.storage import utils
from utilities.infra import Images


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN19_IMG}",
            },
            marks=(pytest.mark.polarion("CNV-1892")),
        ),
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
            },
            marks=(pytest.mark.polarion("CNV-3409")),
        ),
    ],
    indirect=True,
)
def test_successful_clone_of_large_image(
    skip_upstream,
    storage_class_matrix__class__,
    namespace,
    data_volume_multi_storage_scope_class,
):
    storage_class = [*storage_class_matrix__class__][0]
    with utilities.storage.create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_class.size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__class__[storage_class]["volume_mode"],
    ) as cdv:
        cdv.wait(timeout=1500)
        pvc = cdv.pvc
        assert pvc.bound()


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class",
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
    storage_class_matrix__class__,
    namespace,
    data_volume_multi_storage_scope_class,
):
    storage_class = [*storage_class_matrix__class__][0]
    with utilities.storage.create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_class.size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__class__[storage_class]["volume_mode"],
    ) as cdv:
        cdv.wait(timeout=600)
        with utils.create_vm_from_dv(dv=cdv) as vm_dv:
            vm_dv.restart(timeout=300, wait=True)
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_function", "vm_params"),
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "source": "http",
                "image": f"{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
            },
            {
                "vm_name": f"vm-win-{py_config['latest_windows_version']['os_version']}",
                "template_labels": {
                    "os": py_config["latest_windows_version"]["os_label"],
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
                "os_version": py_config["latest_windows_version"]["os_version"],
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
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
):
    with utilities.storage.create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_multi_storage_scope_function.namespace,
        size=data_volume_multi_storage_scope_function.size,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
    ) as cdv:
        cdv.wait(timeout=1600)
        assert cdv.pvc.bound()
        utils.create_windows_vm_validate_guest_agent_info(
            cloud_init_data=cloud_init_data,
            bridge_attached_helper_vm=bridge_attached_helper_vm,
            dv=cdv,
            namespace=namespace,
            network_configuration=network_configuration,
            unprivileged_client=unprivileged_client,
            vm_params=vm_params,
            winrmcli_pod_scope_function=winrmcli_pod_scope_function,
        )
