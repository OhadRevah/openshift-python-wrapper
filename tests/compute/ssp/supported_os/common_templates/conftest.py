# -*- coding: utf-8 -*-

import logging
import os
import shutil

import pytest

from .utils import download_and_extract_tar


LOGGER = logging.getLogger(__name__)


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
