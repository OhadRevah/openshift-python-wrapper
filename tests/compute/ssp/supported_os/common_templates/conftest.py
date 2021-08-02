# -*- coding: utf-8 -*-

import logging
import os
import shutil
from subprocess import CalledProcessError, check_output

import pytest
from ocp_resources.utils import TimeoutSampler

from tests.compute.ssp.supported_os.common_templates.utils import (
    HVINFO_PATH,
    download_and_extract_tar,
)
from utilities.virt import vm_instance_from_template


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def fetch_osinfo_path(tmpdir_factory):
    """Obtain the osinfo path."""

    osinfo_repo = "https://releases.pagure.org/libosinfo/"
    tarfile_name = "osinfo-db-20210809"
    cwd = os.getcwd()
    osinfo_path = tmpdir_factory.mktemp("osinfodb")
    os.chdir(osinfo_path)
    download_and_extract_tar(tarfile_url=f"{osinfo_repo}{tarfile_name}.tar.xz")
    os.chdir(cwd)
    yield os.path.join(osinfo_path, tarfile_name)
    shutil.rmtree(osinfo_path)


@pytest.fixture(scope="class")
def hvinfo_binary_in_executor(tmpdir_factory):
    executor_hvinfo_dir = tmpdir_factory.mktemp("hvinfo")
    executor_hvinfo_path = os.path.join(executor_hvinfo_dir, "hvinfo.exe")
    download_hvinfo_cmd = (
        "wget -N "
        "http://cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com/files/binaries/hvinfo/hvinfo.exe "
        f"-O {executor_hvinfo_path}"
    )

    LOGGER.info(f"Download hvinfo to executor, path: {executor_hvinfo_path}")
    check_output(download_hvinfo_cmd, shell=True)

    yield executor_hvinfo_path

    LOGGER.info("Delete hvinfo from executor")
    shutil.rmtree(path=executor_hvinfo_dir)


@pytest.fixture()
def hvinfo_binary_in_windows_vm(
    golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    hvinfo_binary_in_executor,
):
    def _copy_hvinfo_to_vm():
        copy_hvinfo_cmd = (
            f"sshpass -p {vm.password} scp -P {vm.ssh_service.service_port} -o 'StrictHostKeyChecking no' "
            "-o 'TCPKeepAlive yes' -o 'ServerAliveCountMax 20' -o 'ServerAliveInterval 120' "
            f"{hvinfo_binary_in_executor} {vm.username}@{vm.ssh_service.service_ip()}:{HVINFO_PATH}"
        )
        return check_output(copy_hvinfo_cmd, shell=True) == b""

    vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class

    LOGGER.info("Copy hvinfo to VM")
    for sample in TimeoutSampler(
        wait_timeout=120,
        sleep=1,
        func=_copy_hvinfo_to_vm,
        exceptions=CalledProcessError,
    ):
        if sample:
            break


@pytest.fixture()
def vm_from_template_with_existing_dv(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
):
    """create VM from template using an existing DV (and not a golden image)"""
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_function,
    ) as vm:
        yield vm
