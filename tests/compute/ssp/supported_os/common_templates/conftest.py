# -*- coding: utf-8 -*-

import logging
import os
import shutil

import pytest

from .utils import download_and_extract_tar, wait_for_windows_vm


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def started_windows_vm(
    request,
    vm_instance_from_template_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_scope_function,
        version=request.param["os_version"],
        winrmcli_pod=winrmcli_pod_scope_function,
        timeout=1800,
        helper_vm=bridge_attached_helper_vm,
    )


@pytest.fixture(scope="module")
def fetch_osinfo_path(tmpdir_factory):
    """ Obtain the osinfo path. """

    osinfo_repo = "https://releases.pagure.org/libosinfo/"
    tarfile_name = "osinfo-db-20200203"
    cwd = os.getcwd()
    osinfo_path = tmpdir_factory.mktemp("osinfodb")
    os.chdir(osinfo_path)
    download_and_extract_tar(f"{osinfo_repo}{tarfile_name}.tar.xz")
    os.chdir(cwd)
    yield os.path.join(osinfo_path, tarfile_name)
    shutil.rmtree(osinfo_path)
