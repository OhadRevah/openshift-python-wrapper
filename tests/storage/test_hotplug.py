"""
Automation for Hot Plug
"""
import shlex

import pytest
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutSampler

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from tests.storage.utils import storage_params
from utilities.constants import TIMEOUT_2MIN
from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
    run_ssh_commands,
)
from utilities.storage import create_dv, virtctl_volume
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


pytestmark = pytest.mark.post_upgrade


SERIAL = "1234567890"


def vm_volume_ready(vm):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=lambda: vm.vmi.instance,
    )
    for sample in sampler:
        if sample.status.volumeStatus[0]["reason"] == "VolumeReady":
            return


def assert_disk_serial(vm, command=shlex.split("sudo ls /dev/disk/by-id")):
    assert (
        SERIAL in run_ssh_commands(host=vm.ssh_exec, commands=command)[0]
    ), "hotplug disk serial id is not in VM"


def assert_hotplugvolume_nonexist_after_restart(vm):
    vm.restart(wait=True)
    assert (
        "hotplugVolume" not in vm.vmi.instance.status.volumeStatus[0]
    ), "hotplug disk should become a regular disk for VM after restart"


@pytest.fixture()
def skip_if_hpp_sc(storage_class_matrix__function__):
    bug_id = 1955129
    if [*storage_class_matrix__function__][
        0
    ] == StorageClass.Types.HOSTPATH and get_bug_status(
        bugzilla_connection_params=get_bugzilla_connection_params(), bug=bug_id
    ) not in BUG_STATUS_CLOSED:
        pytest.skip(f"Skip the test due to bug {bug_id}")


@pytest.fixture()
def blank_disk_dv(namespace, storage_class_matrix__function__):
    with create_dv(
        source="blank",
        dv_name="blank-dv",
        namespace=namespace.name,
        size="1Gi",
        **storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        yield dv


@pytest.fixture()
def fedora_vm_for_hotplug(namespace):
    name = "fedora-hotplug"
    with VirtualMachineForTests(
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


@pytest.mark.polarion("CNV-5508")
def test_hotplugvolumes_feature_gate(kubevirt_feature_gates):
    hotplug_volumes = "HotplugVolumes"
    assert (
        "HotplugVolumes" in kubevirt_feature_gates
    ), f"{hotplug_volumes} not in {kubevirt_feature_gates}"


@pytest.mark.polarion("CNV-6013")
@pytest.mark.parametrize(
    "hotplug_volume",
    [{"serial": SERIAL}],
    indirect=True,
)
def test_hotplug_volume_with_serial(
    skip_if_hpp_sc,
    namespace,
    blank_disk_dv,
    fedora_vm_for_hotplug,
    hotplug_volume,
):
    vm_volume_ready(vm=fedora_vm_for_hotplug)
    assert_disk_serial(vm=fedora_vm_for_hotplug)


@pytest.mark.polarion("CNV-6014")
@pytest.mark.parametrize(
    "hotplug_volume",
    [{"persist": True}],
    indirect=True,
)
def test_hotplug_volume_with_persist(
    skip_if_hpp_sc,
    namespace,
    blank_disk_dv,
    fedora_vm_for_hotplug,
    hotplug_volume,
):
    vm_volume_ready(vm=fedora_vm_for_hotplug)
    assert_hotplugvolume_nonexist_after_restart(vm=fedora_vm_for_hotplug)


@pytest.mark.polarion("CNV-6425")
@pytest.mark.parametrize(
    "hotplug_volume",
    [{"persist": True, "serial": SERIAL}],
    indirect=True,
)
def test_hotplug_volume_with_serial_and_persist(
    skip_if_hpp_sc,
    namespace,
    blank_disk_dv,
    fedora_vm_for_hotplug,
    hotplug_volume,
):
    vm_volume_ready(vm=fedora_vm_for_hotplug)
    assert_disk_serial(vm=fedora_vm_for_hotplug)
    assert_hotplugvolume_nonexist_after_restart(vm=fedora_vm_for_hotplug)


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
            {"persist": True, "serial": SERIAL},
            marks=pytest.mark.polarion("CNV-6525"),
        ),
    ],
    indirect=True,
)
def test_windows_hotplug(
    skip_upstream,
    skip_if_hpp_sc,
    unprivileged_client,
    namespace,
    blank_disk_dv,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    started_windows_vm,
    hotplug_volume_windows,
):
    vm_volume_ready(vm=vm_instance_from_template_multi_storage_scope_function)
    assert_disk_serial(
        command=shlex.split("wmic diskdrive get SerialNumber"),
        vm=vm_instance_from_template_multi_storage_scope_function,
    )
    assert_hotplugvolume_nonexist_after_restart(
        vm=vm_instance_from_template_multi_storage_scope_function
    )
