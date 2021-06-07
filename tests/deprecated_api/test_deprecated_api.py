import json
import logging
import os
import shutil
import subprocess
import tarfile

import pytest


LOGGER = logging.getLogger(__name__)
OC_RAW_CMD = "oc get --raw"
METRICS = "metrics"


@pytest.fixture(scope="module")
def prom2json(tmpdir_factory):
    file_name = "prom2json"
    version = "1.3.0"
    path = tmpdir_factory.mktemp(file_name)
    tar_prefix = f"prom2json-{version}.linux-amd64"
    tar_file_name = f"{tar_prefix}.tar.gz"
    tar_file_path = os.path.join(path, tar_file_name)
    cmd = (
        "wget -N"
        f" https://github.com/prometheus/prom2json/releases/download/v{version}/{tar_file_name}"
        f" -O {tar_file_path}"
    )
    LOGGER.info(f"Downloading {tar_file_name}")
    subprocess.check_output(cmd, shell=True)

    LOGGER.info(f"Extract {tar_file_path}")
    tar = tarfile.open(tar_file_path)
    tar.extractall(path=path)
    yield os.path.join(path, tar_prefix, file_name)
    shutil.rmtree(path=path)


@pytest.fixture(scope="module")
def deprecated_apis(prom2json):
    LOGGER.info("Checking for deprecated APIs")
    data = json.loads(s=subprocess.getoutput(f"{OC_RAW_CMD} /{METRICS} | {prom2json}"))
    return [api for api in data if api["name"] == "apiserver_requested_deprecated_apis"]


@pytest.mark.last
@pytest.mark.polarion("CNV-6557")
def test_deprecated_api(deprecated_apis):
    err_msg = ""
    if deprecated_apis:
        metrics = deprecated_apis[0][METRICS]
        for metric in metrics:
            labels = metric["labels"]
            if labels["removed_release"] == "1.22":
                err_msg += f"{labels}\n"

    if err_msg:
        pytest.fail(err_msg)
