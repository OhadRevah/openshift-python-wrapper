"""
Automation for Hot Plug
"""
import shlex

import pytest
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutSampler

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
def vm_volume_ready(fedora_vm_for_hotplug):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=lambda: fedora_vm_for_hotplug.vmi.instance,
    )
    for sample in sampler:
        if sample.status.volumeStatus[0]["reason"] == "VolumeReady":
            return


@pytest.fixture()
def vm_restart(fedora_vm_for_hotplug):
    fedora_vm_for_hotplug.restart(wait=True)


@pytest.fixture()
def vm_disk_serial(fedora_vm_for_hotplug):
    commands = shlex.split("sudo ls /dev/disk/by-id")
    return run_ssh_commands(host=fedora_vm_for_hotplug.ssh_exec, commands=commands)[0]


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
    vm_volume_ready,
    vm_disk_serial,
):
    assert SERIAL in vm_disk_serial, "hotplug disk serial id is not in VM"


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
    vm_volume_ready,
    vm_restart,
):
    assert (
        "hotplugVolume" not in fedora_vm_for_hotplug.vmi.instance.status.volumeStatus[0]
    ), "hotplug disk should become a regular disk for VM after restart"


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
    vm_volume_ready,
    vm_disk_serial,
):
    assert SERIAL in vm_disk_serial, "hotplug disk serial id is not in VM"
    fedora_vm_for_hotplug.restart(wait=True)
    assert (
        "hotplugVolume" not in fedora_vm_for_hotplug.vmi.instance.status.volumeStatus[0]
    ), "hotplug disk should become a regular disk for VM after restart"
