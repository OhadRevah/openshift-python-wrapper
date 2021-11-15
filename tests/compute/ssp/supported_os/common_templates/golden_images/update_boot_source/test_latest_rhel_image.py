import os
import re
import shlex
from pathlib import Path

import pytest

from utilities.constants import Images
from utilities.infra import run_ssh_commands
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture()
def latest_rhel_8_vm(unprivileged_client, namespace):
    with VirtualMachineForTests(
        name="latest-rhel-8-vm",
        client=unprivileged_client,
        namespace=namespace.name,
        image="registry.redhat.io/rhel8/rhel-guest-image",
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def latest_rhel8_minor_ver_num(downloaded_latest_libosinfo_db):
    osinfo_file_folder_path = os.path.join(
        f"{downloaded_latest_libosinfo_db}/os/redhat.com/"
    )

    list_of_rhel8_os_files = list(
        sorted(Path(osinfo_file_folder_path).glob("rhel-8.*.xml"))
    )
    latest_rhel8_os_file = list_of_rhel8_os_files[-1]
    return re.findall(
        r"(?<=rhel-8\.)(\d+[\.]?[\d+]?)(?=\.xml)", latest_rhel8_os_file.name
    )[0]


@pytest.fixture()
def rhel8_vm_minor_ver_num(latest_rhel_8_vm):
    rhel8_vm_os_ver = run_ssh_commands(
        host=latest_rhel_8_vm.ssh_exec,
        commands=(shlex.split("cat /etc/redhat-release")),
    )[0]
    return re.findall(r"(?<=\.)(\d+[\.]?[\d+]?)(?= )", rhel8_vm_os_ver)[0]


@pytest.mark.polarion("CNV-7666")
def test_latest_minor_ver_rhel(latest_rhel8_minor_ver_num, rhel8_vm_minor_ver_num):
    assert latest_rhel8_minor_ver_num == rhel8_vm_minor_ver_num, (
        f"os versions mismatch, VM minor version: {rhel8_vm_minor_ver_num}, "
        f"osinfo DB latest minor version: {latest_rhel8_minor_ver_num}"
    )
