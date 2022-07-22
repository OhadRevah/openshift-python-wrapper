import os
import re

import pytest
import requests
from bs4 import BeautifulSoup
from pytest_testconfig import py_config

from tests.compute.ssp.utils import download_and_extract_tar


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract SMBIOS default from kubevirt CR."""
    return kubevirt_config_scope_module["smbios"]


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract machine type default from kubevirt CR."""
    return kubevirt_config_scope_module["machineType"]


@pytest.fixture(scope="module")
def downloaded_latest_libosinfo_db(
    tmpdir_factory, latest_osinfo_db_file_name, osinfo_repo
):
    """Obtain the osinfo path."""
    osinfo_path = tmpdir_factory.mktemp("osinfodb")
    download_and_extract_tar(
        tarfile_url=f"{osinfo_repo}{latest_osinfo_db_file_name}",
        dest_path=osinfo_path,
    )
    osinfo_db_file_name_no_suffix = latest_osinfo_db_file_name.partition(".")[0]
    yield os.path.join(osinfo_path, osinfo_db_file_name_no_suffix)


@pytest.fixture(scope="module")
def latest_osinfo_db_file_name(osinfo_repo):
    sorted_osinfo_repo = f"{osinfo_repo}/?C=M;O=D"
    soup_page = BeautifulSoup(
        markup=requests.get(sorted_osinfo_repo).text, features="html.parser"
    )
    full_link = soup_page.find(
        "a", {"href": re.compile(r"osinfo-db-[0-9]*.tar.xz")}
    ).get("href")
    return full_link


@pytest.fixture(scope="module")
def osinfo_repo():
    return f"{py_config['servers']['http_server']}cnv-tests/osinfo-db/"
