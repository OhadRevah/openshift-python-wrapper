# -*- coding: utf-8 -*-

""" CDIConfig tests """
import logging

import pytest

from resources.cdi_config import CDIConfig
from resources.route import Route

LOGGER = logging.getLogger(__name__)

CONFIG_NAME = "config"


@pytest.mark.polarion("CNV-2208")
def test_cdi_config_exists(upload_proxy_route):
    cdi_config = CDIConfig(CONFIG_NAME)
    assert cdi_config.instance is not None
    assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.polarion("CNV-2209")
def test_different_route_for_upload_proxy(storage_ns, uploadproxy_route_deleted):
    cdi_config = CDIConfig(CONFIG_NAME)
    with Route(
        namespace=storage_ns.name, name="my-route", service="cdi-uploadproxy"
    ) as new_route:
        assert cdi_config.wait_until_upload_url_changed(new_route.host)


@pytest.mark.polarion("CNV-2215")
def test_route_for_different_service(upload_proxy_route):
    cdi_config = CDIConfig(CONFIG_NAME)
    with Route(
        namespace=upload_proxy_route.namespace, name="cdi-api", service="cdi-api"
    ) as cdi_api_route:
        assert cdi_config.upload_proxy_url != cdi_api_route.host
        assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.polarion("CNV-2216")
def test_upload_proxy_url_overridden(storage_ns, cdi_config_upload_proxy_overridden):
    cdi_config = CDIConfig(CONFIG_NAME)
    with Route(
        namespace=storage_ns.name, name="my-route", service="cdi-uploadproxy"
    ) as new_route:
        assert cdi_config.upload_proxy_url != new_route.host
