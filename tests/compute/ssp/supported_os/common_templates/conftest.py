# -*- coding: utf-8 -*-
import logging
import os
import shutil
from subprocess import CalledProcessError, check_output

import pytest
from ocp_resources.utils import TimeoutSampler

from tests.compute.ssp.supported_os.common_templates.utils import HVINFO_PATH


LOGGER = logging.getLogger(__name__)


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
            f"sshpass -p {vm.password} scp -o 'StrictHostKeyChecking no' -o 'ServerAliveCountMax 20' "
            f"-o 'TCPKeepAlive yes' -o 'ServerAliveInterval 120' -o 'ProxyCommand={vm.virtctl_port_forward_cmd}' "
            f"{hvinfo_binary_in_executor} {vm.username}@{vm.name}:{HVINFO_PATH}"
        )
        return check_output(copy_hvinfo_cmd, shell=True) == b""

    vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class

    LOGGER.info("Copy hvinfo to VM")
    for sample in TimeoutSampler(
        wait_timeout=120,
        sleep=1,
        func=_copy_hvinfo_to_vm,
        exceptions_dict={CalledProcessError: []},
    ):
        if sample:
            break
