# -*- coding: utf-8 -*-

"""
must gather test
"""

import logging
import pytest
import shutil
from subprocess import check_output

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope='module') # noqa BLK100
def cnv_must_gather(tmpdir_factory):
    """
    Run cnv-must-gather for data collection.
    """
    LOGGER.info('Running cnv_must_gather')
    image = 'quay.io/kubevirt/must-gather'
    path = tmpdir_factory.mktemp('must_gather')
    try:
        mg_cmd = f'oc adm must-gather --image={image} --dest-dir={path}'
        check_output(mg_cmd, shell=True)
        yield path
    finally:
        shutil.rmtree(path)
