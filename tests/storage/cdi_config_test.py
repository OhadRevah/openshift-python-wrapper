# -*- coding: utf-8 -*-

""" CDIConfig tests """
import pytest

from resources.cdi_config import CDIConfig


CONFIG_NAME = 'config'


@pytest.mark.polarion("CNV-2208")
def test_cdi_config_exists(upload_proxy_route):
    cdi_config = CDIConfig(CONFIG_NAME)
    assert cdi_config.instance is not None
    assert cdi_config.upload_proxy_url == upload_proxy_route.host
