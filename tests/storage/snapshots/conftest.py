# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage snapshots tests
"""
import logging
import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.role_binding import RoleBinding
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.storage.snapshots.constants import WINDOWS_DIRECTORY_PATH
from tests.storage.snapshots.utils import assert_directory_existence
from tests.storage.utils import create_cirros_vm, set_permissions
from utilities.constants import TIMEOUT_10MIN, UNPRIVILEGED_USER, Images
from utilities.infra import run_ssh_commands
from utilities.storage import create_cirros_ceph_dv, get_images_server_url, write_file
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm


LOGGER = logging.getLogger(__name__)


def check_snapshot_indication(snapshot, is_online):
    snapshot_indications = snapshot.instance.status.indications
    if is_online:
        assert "Online" in snapshot_indications
    else:
        assert not snapshot_indications


@pytest.fixture()
def cirros_dv(
    namespace,
    cirros_vm_name,
):
    yield create_cirros_ceph_dv(name=cirros_vm_name, namespace=namespace.name)


@pytest.fixture()
def cirros_vm(
    admin_client,
    namespace,
    cirros_vm_name,
    cirros_dv,
):
    """
    Create a VM with a DV from the cirros_dv fixture
    """
    with create_cirros_vm(
        admin_client=admin_client, cirros_dv=cirros_dv, cirros_vm_name=cirros_vm_name
    ) as vm:
        yield vm


@pytest.fixture()
def snapshots_with_content(
    request,
    namespace,
    admin_client,
    cirros_vm,
):
    """
    Creates a requested number of snapshots with content
    The default behavior of the fixture is creating an offline
    snapshot unless {online_vm = True} declared in the test
    """
    vm_snapshots = []
    is_online_test = request.param.get("online_vm", False)
    for idx in range(request.param["number_of_snapshots"]):
        # write_file check if the vm is running and if not, start the vm
        # after the file have been written the function stops the vm
        write_file(
            vm=cirros_vm,
            filename=f"before-snap-{idx+1}.txt",
            content=f"before-snap-{idx+1}",
        )
        if is_online_test:
            cirros_vm.start(wait=True)
        with VirtualMachineSnapshot(
            name=f"snapshot-{cirros_vm.name}-number-{idx+1}",
            namespace=cirros_vm.namespace,
            vm_name=cirros_vm.name,
            client=admin_client,
            teardown=False,
        ) as vm_snapshot:
            vm_snapshots.append(vm_snapshot)
            vm_snapshot.wait_ready_to_use()
            write_file(
                vm=cirros_vm,
                filename=f"after-snap-{idx+1}.txt",
                content=f"after-snap-{idx+1}",
            )
    check_snapshot_indication(snapshot=vm_snapshot, is_online=is_online_test)
    yield vm_snapshots

    for vm_snapshot in vm_snapshots:
        vm_snapshot.clean_up()


@pytest.fixture()
def permissions_for_dv(namespace):
    """
    Sets DV permissions for an unprivileged client
    """
    with set_permissions(
        role_name="datavolume-cluster-role",
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role-bind-data-volume",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RoleBinding.api_group,
    ):
        yield


@pytest.fixture()
def windows_ceph_vm(
    request,
    namespace,
    unprivileged_client,
    nodes_common_cpu_model,
):
    dv = DataVolume(
        name=request.param["dv_name"],
        namespace=namespace.name,
        storage_class=StorageClass.Types.CEPH_RBD,
        source="http",
        url=f"{get_images_server_url(schema='http')}{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
        size=Images.Windows.DEFAULT_DV_SIZE,
        client=unprivileged_client,
        api_name="storage",
    ).to_dict()
    with VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"],
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_windows_os_dict"]["template_labels"]
        ),
        cpu_model=nodes_common_cpu_model,
        data_volume_template={"metadata": dv["metadata"], "spec": dv["spec"]},
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def snapshot_windows_directory(windows_ceph_vm):
    cmd = shlex.split(
        f'powershell -command "New-Item -Path {WINDOWS_DIRECTORY_PATH} -ItemType Directory"',
    )
    run_ssh_commands(host=windows_ceph_vm.ssh_exec, commands=cmd)
    assert_directory_existence(
        expected_result=True,
        windows_vm=windows_ceph_vm,
        directory_path=WINDOWS_DIRECTORY_PATH,
    )


@pytest.fixture()
def windows_snapshot(
    snapshot_windows_directory,
    windows_ceph_vm,
):
    with VirtualMachineSnapshot(
        name="windows-snapshot",
        namespace=windows_ceph_vm.namespace,
        vm_name=windows_ceph_vm.name,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def snapshot_dirctory_removed(windows_ceph_vm, windows_snapshot):
    windows_snapshot.wait_ready_to_use(timeout=TIMEOUT_10MIN)
    cmd = shlex.split(
        f'powershell -command "Remove-Item -Path {WINDOWS_DIRECTORY_PATH} -Recurse"',
    )
    run_ssh_commands(host=windows_ceph_vm.ssh_exec, commands=cmd)
    assert_directory_existence(
        expected_result=False,
        windows_vm=windows_ceph_vm,
        directory_path=WINDOWS_DIRECTORY_PATH,
    )
    windows_ceph_vm.stop(wait=True)


@pytest.fixture()
def file_created_during_snapshot(windows_ceph_vm, windows_snapshot):
    file = f"{WINDOWS_DIRECTORY_PATH}\\file.txt"
    cmd = shlex.split(
        f'powershell -command "for($i=1; $i -le 100; $i++){{$i| Out-File -FilePath {file} -Append}}"',
    )
    run_ssh_commands(host=windows_ceph_vm.ssh_exec, commands=cmd)
    windows_snapshot.wait_ready_to_use(timeout=TIMEOUT_10MIN)
    windows_ceph_vm.stop(wait=True)
