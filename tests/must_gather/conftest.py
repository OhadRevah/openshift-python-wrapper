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
def cnv_must_gather(tmpdir_factory):
    """
    Run cnv-must-gather for data collection.
    """
    image = py_config["must_gather"]["url"]
    version = py_config["must_gather"].get("version")
    if version:
        image = f"{image}:{version}"

    path = tmpdir_factory.mktemp("must_gather")
    try:
        must_gather_cmd = f"oc adm must-gather --image={image} --dest-dir={path}"
        LOGGER.info(f"Running: {must_gather_cmd}")
        check_output(must_gather_cmd, shell=True)
        yield path
    finally:
        shutil.rmtree(path)
