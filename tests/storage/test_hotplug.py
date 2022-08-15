"""
Automation for Hot Plug
"""
import shlex

import pytest

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from utilities.constants import HOTPLUG_DISK_SERIAL
from utilities.infra import cluster_resource
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist_optional_restart,
    create_dv,
    virtctl_volume,
    wait_for_vm_volume_ready,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


pytestmark = pytest.mark.post_upgrade


@pytest.fixture()
def blank_disk_dv(namespace, storage_class_matrix__function__):
    with create_dv(
        source="blank",
        dv_name="blank-dv",
        namespace=namespace.name,
        size="1Gi",
        storage_class=[*storage_class_matrix__function__][0],
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.fixture()
def fedora_vm_for_hotplug(namespace):
    name = "fedora-hotplug"
    with cluster_resource(VirtualMachineForTests)(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def hotplug_volume(request, namespace, fedora_vm_for_hotplug):
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=fedora_vm_for_hotplug.name,
        volume_name="blank-dv",
        **request.param,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.fixture()
def hotplug_volume_windows(
    request, namespace, vm_instance_from_template_multi_storage_scope_function
):
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=vm_instance_from_template_multi_storage_scope_function.name,
        volume_name="blank-dv",
        **request.param,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.mark.sno
@pytest.mark.polarion("CNV-5508")
def test_hotplugvolumes_feature_gate(kubevirt_feature_gates):
    hotplug_volumes = "HotplugVolumes"
    assert (
        "HotplugVolumes" in kubevirt_feature_gates
    ), f"{hotplug_volumes} not in {kubevirt_feature_gates}"


@pytest.mark.sno
@pytest.mark.polarion("CNV-6013")
@pytest.mark.parametrize(
    "hotplug_volume",
    [{"serial": HOTPLUG_DISK_SERIAL}],
    indirect=True,
)
def test_hotplug_volume_with_serial(
    namespace,
    blank_disk_dv,
    fedora_vm_for_hotplug,
    hotplug_volume,
):
    wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug)
    assert_disk_serial(vm=fedora_vm_for_hotplug)


@pytest.mark.sno
@pytest.mark.polarion("CNV-6014")
@pytest.mark.parametrize(
    "hotplug_volume",
    [{"persist": True}],
    indirect=True,
)
def test_hotplug_volume_with_persist(
    namespace,
    blank_disk_dv,
    fedora_vm_for_hotplug,
    hotplug_volume,
):
    wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug)
    assert_hotplugvolume_nonexist_optional_restart(
        vm=fedora_vm_for_hotplug, restart=True
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-6425")
@pytest.mark.parametrize(
    "hotplug_volume",
    [{"persist": True, "serial": HOTPLUG_DISK_SERIAL}],
    indirect=True,
)
def test_hotplug_volume_with_serial_and_persist(
    namespace,
    blank_disk_dv,
    fedora_vm_for_hotplug,
    hotplug_volume,
):
    wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug)
    assert_disk_serial(vm=fedora_vm_for_hotplug)
    assert_hotplugvolume_nonexist_optional_restart(
        vm=fedora_vm_for_hotplug, restart=True
    )


@pytest.mark.tier3
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm,"
    "hotplug_volume_windows",
    [
        pytest.param(
            {
                "dv_name": "dv-windows",
                "image": WINDOWS_LATEST["image_path"],
                "dv_size": WINDOWS_LATEST["dv_size"],
            },
            {
                "vm_name": f"vm-win-{WINDOWS_LATEST['os_version']}",
                "template_labels": WINDOWS_LATEST_LABELS,
            },
            {"os_version": WINDOWS_LATEST["os_version"]},
            {"persist": True, "serial": HOTPLUG_DISK_SERIAL},
            marks=pytest.mark.polarion("CNV-6525"),
        ),
    ],
    indirect=True,
)
def test_windows_hotplug(
    skip_upstream,
    unprivileged_client,
    namespace,
    blank_disk_dv,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    started_windows_vm,
    hotplug_volume_windows,
):
    wait_for_vm_volume_ready(vm=vm_instance_from_template_multi_storage_scope_function)
    assert_disk_serial(
        command=shlex.split("wmic diskdrive get SerialNumber"),
        vm=vm_instance_from_template_multi_storage_scope_function,
    )
    assert_hotplugvolume_nonexist_optional_restart(
        vm=vm_instance_from_template_multi_storage_scope_function,
        restart=True,
    )
