import logging
import shutil
from collections import defaultdict

import pytest
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template

from tests.compute.utils import (
    fetch_processid_from_linux_vm,
    fetch_processid_from_windows_vm,
    generate_attached_rhsm_secret_dict,
    generate_rhsm_cloud_init_data,
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
)
from tests.compute.virt.utils import migrate_and_verify_multi_vms
from tests.os_params import (
    RHEL_8_5,
    RHEL_8_5_TEMPLATE_LABELS,
    WINDOWS_10,
    WINDOWS_10_TEMPLATE_LABELS,
)
from utilities.storage import create_or_update_data_source, data_volume
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    running_vm,
)


pytestmark = [
    pytest.mark.usefixtures("skip_if_workers_vms"),
    pytest.mark.longevity,
]


LOGGER = logging.getLogger(__name__)
LINUX_OS_PREFIX = "lin"
WINDOWS_OS_PREFIX = "win"

PROC_PER_OS_DICT = {
    LINUX_OS_PREFIX: {
        "proc_name": "sleep",
        "proc_args": "infinity",
        "fetch_pid": fetch_processid_from_linux_vm,
        "create_proc": start_and_fetch_processid_on_linux_vm,
    },
    WINDOWS_OS_PREFIX: {
        "proc_name": "notepad",
        "fetch_pid": fetch_processid_from_windows_vm,
        "create_proc": start_and_fetch_processid_on_windows_vm,
    },
}


def run_migration_loop(iterations, vms_with_pids, os_type):
    def decorate_log(msg):
        terminal_width = int(shutil.get_terminal_size(fallback=(120, 40))[0])
        msg_decor = "-" * round(terminal_width / 4 - 30)
        return f"{msg_decor}{msg}{msg_decor}"

    for iteration in range(iterations):
        LOGGER.info(decorate_log(f"Iteration {iteration + 1}"))
        LOGGER.info(decorate_log("VM Migration"))
        migrate_and_verify_multi_vms(
            vm_list=[vms_with_pids[vm_name]["vm"] for vm_name in vms_with_pids]
        )
        LOGGER.info(decorate_log("PID check"))
        verify_pid_after_migrate_multi_vms(vms_with_pids=vms_with_pids, os_type=os_type)


def start_process_in_guest(vm, os_type):
    vm_and_pid = defaultdict(dict)
    os_dict = PROC_PER_OS_DICT[os_type]
    params = {"vm": vm, "process_name": os_dict["proc_name"]}
    if os_dict.get("proc_args"):
        params.update({"args": os_dict["proc_args"]})

    vm_and_pid[vm.name]["vm"] = vm
    vm_and_pid[vm.name]["pid"] = os_dict["create_proc"](**params)
    return vm_and_pid


def verify_pid_after_migrate_multi_vms(vms_with_pids, os_type):
    vms_with_wrong_pids_dict = {}
    os_dict = PROC_PER_OS_DICT[os_type]

    for vm_name in vms_with_pids:
        orig_pid = vms_with_pids[vm_name]["pid"]
        new_pid = os_dict["fetch_pid"](
            vm=vms_with_pids[vm_name]["vm"], process_name=os_dict["proc_name"]
        )
        if orig_pid != new_pid:
            vms_with_wrong_pids_dict[vm_name] = {
                "orig_pid": orig_pid,
                "new_pid": new_pid,
            }

    assert (
        not vms_with_wrong_pids_dict
    ), f"Some VMs have wrong pids after migration - {vms_with_wrong_pids_dict}"


def start_vms_with_processes(vms_list, os_type):
    vms_and_pids = {}

    for vm in vms_list:
        running_vm(vm=vm)
        vms_and_pids.update(start_process_in_guest(vm=vm, os_type=os_type))

    yield vms_and_pids

    for vm in vms_list:
        vm.clean_up()


def create_containerdisk_vm(request, client, name, namespace):
    deployed_vm = VirtualMachineForTests(
        name=f"{request.param['vm_name_prefix']}-{name}",
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=client,
        eviction=True,
        running=True,
    )
    deployed_vm.deploy()
    return deployed_vm


def create_dv_vm(
    request,
    client,
    name,
    namespace,
    data_source,
    cloud_init_data=None,
    attached_secret=None,
):
    deployed_vm = VirtualMachineForTestsFromTemplate(
        name=f"{request.param['vm_name_prefix']}-{name}",
        labels=Template.generate_template_labels(**request.param["os_labels"]),
        namespace=namespace.name,
        client=client,
        data_source=data_source,
        cloud_init_data=cloud_init_data,
        attached_secret=attached_secret,
    )
    deployed_vm.deploy()
    deployed_vm.start()
    return deployed_vm


@pytest.fixture()
def vm_request(request):
    """
    Fixture is used to store VM related params that are common for all test VMs.
    This is needed to not pass params via pytest.mark.parametrize to each VM fixture separately
    """
    return request


@pytest.fixture()
def nfs_vm(vm_request, namespace, unprivileged_client, golden_image_data_source_nfs):
    LOGGER.info("Deploying VM with NFS disk")
    return create_dv_vm(
        request=vm_request,
        client=unprivileged_client,
        namespace=namespace,
        name="nfsdisk",
        data_source=golden_image_data_source_nfs,
    )


@pytest.fixture()
def ocs_vm(vm_request, namespace, unprivileged_client, golden_image_data_source_ocs):
    LOGGER.info("Deploying VM with OCS disk")
    return create_dv_vm(
        request=vm_request,
        client=unprivileged_client,
        namespace=namespace,
        name="ocsdisk",
        data_source=golden_image_data_source_ocs,
    )


@pytest.fixture()
def secret_vm(
    vm_request,
    namespace,
    unprivileged_client,
    golden_image_data_source_ocs,
    rhsm_created_secret,
):
    LOGGER.info("Deploying VM with secret")
    return create_dv_vm(
        request=vm_request,
        client=unprivileged_client,
        namespace=namespace,
        name="secret",
        data_source=golden_image_data_source_ocs,
        cloud_init_data=generate_rhsm_cloud_init_data(),
        attached_secret=generate_attached_rhsm_secret_dict(),
    )


@pytest.fixture()
def container_vm(vm_request, namespace, unprivileged_client):
    LOGGER.info("Deploying VM with container disk")
    return create_containerdisk_vm(
        request=vm_request,
        client=unprivileged_client,
        namespace=namespace,
        name="containerdisk",
    )


@pytest.fixture()
def linux_vms_with_pids(
    cluster_cpu_model_scope_module, nfs_vm, ocs_vm, secret_vm, container_vm
):
    yield from start_vms_with_processes(
        vms_list=[nfs_vm, ocs_vm, secret_vm, container_vm], os_type=LINUX_OS_PREFIX
    )


@pytest.fixture()
def windows_vms_with_pids(cluster_cpu_model_scope_module, nfs_vm, ocs_vm):
    yield from start_vms_with_processes(
        vms_list=[nfs_vm, ocs_vm], os_type=WINDOWS_OS_PREFIX
    )


@pytest.fixture()
def golden_image_data_volume_ocs(request, admin_client, golden_images_namespace):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=StorageClass.Types.CEPH_RBD,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_source_ocs(admin_client, golden_image_data_volume_ocs):
    yield from create_or_update_data_source(
        admin_client=admin_client, dv=golden_image_data_volume_ocs
    )


@pytest.fixture()
def golden_image_data_volume_nfs(request, admin_client, golden_images_namespace):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=StorageClass.Types.NFS,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_source_nfs(admin_client, golden_image_data_volume_nfs):
    yield from create_or_update_data_source(
        admin_client=admin_client, dv=golden_image_data_volume_nfs
    )


@pytest.mark.parametrize(
    "iterations, vm_request, golden_image_data_volume_ocs, golden_image_data_volume_nfs",
    [
        pytest.param(
            250,
            {
                "vm_name_prefix": f"{LINUX_OS_PREFIX}-multi-mig-vm",
                "os_labels": RHEL_8_5_TEMPLATE_LABELS,
            },
            {
                "dv_name": f"dv-ocs-{LINUX_OS_PREFIX}",
                "image": RHEL_8_5["image_path"],
                "dv_size": RHEL_8_5["dv_size"],
            },
            {
                "dv_name": f"dv-nfs-{LINUX_OS_PREFIX}",
                "image": RHEL_8_5["image_path"],
                "dv_size": RHEL_8_5["dv_size"],
            },
            marks=pytest.mark.polarion("CNV-8310"),
        )
    ],
    indirect=[
        "vm_request",
        "golden_image_data_volume_ocs",
        "golden_image_data_volume_nfs",
    ],
)
def test_migration_storm_linux_vms(iterations, linux_vms_with_pids):
    run_migration_loop(
        iterations=iterations,
        vms_with_pids=linux_vms_with_pids,
        os_type=LINUX_OS_PREFIX,
    )


@pytest.mark.parametrize(
    "iterations, vm_request, golden_image_data_volume_ocs, golden_image_data_volume_nfs",
    [
        pytest.param(
            500,
            {
                "vm_name_prefix": f"{WINDOWS_OS_PREFIX}-multi-mig-vm",
                "os_labels": WINDOWS_10_TEMPLATE_LABELS,
            },
            {
                "dv_name": f"dv-ocs-{WINDOWS_OS_PREFIX}",
                "image": WINDOWS_10["image_path"],
                "dv_size": WINDOWS_10["dv_size"],
            },
            {
                "dv_name": f"dv-nfs-{WINDOWS_OS_PREFIX}",
                "image": WINDOWS_10["image_path"],
                "dv_size": WINDOWS_10["dv_size"],
            },
            marks=pytest.mark.polarion("CNV-8311"),
        )
    ],
    indirect=[
        "vm_request",
        "golden_image_data_volume_ocs",
        "golden_image_data_volume_nfs",
    ],
)
def test_migration_storm_windows_vms(iterations, windows_vms_with_pids):
    run_migration_loop(
        iterations=iterations,
        vms_with_pids=windows_vms_with_pids,
        os_type=WINDOWS_OS_PREFIX,
    )
