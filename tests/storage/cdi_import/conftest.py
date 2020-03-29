"""
CDI Import
"""

import pytest
from resources.configmap import ConfigMap


@pytest.fixture()
def https_config_map(request, namespace):
    data = request.param["data"] if request else None
    with ConfigMap(
        name="https-cert", namespace=namespace.name, cert_name="ca.pem", data=data,
    ) as configmap:
        yield configmap
