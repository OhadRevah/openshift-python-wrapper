# -*- coding: utf-8 -*-

"""
must gather test
"""

import logging
import shutil
from subprocess import check_output

import pytest
from pytest_testconfig import config as py_config

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cnv_must_gather(tmpdir_factory, cnv_containers):
    """
    Run cnv-must-gather for data collection.
    """
    if py_config["distribution"] == "upstream":
        image = "quay.io/kubevirt/must-gather"
    else:
        image = cnv_containers["cnv-must-gather"]

    path = tmpdir_factory.mktemp("must_gather")
    try:
        must_gather_cmd = f"oc adm must-gather --image={image} --dest-dir={path}"
        LOGGER.info(f"Running: {must_gather_cmd}")
        check_output(must_gather_cmd, shell=True)
        yield path
    finally:
        shutil.rmtree(path)
