# -*- coding: utf-8 -*-
import logging

from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


class Service(NamespacedResource):
    """
    OpenShift Service object.
    """

    api_version = "v1"


class HttpService(Service):
    def _to_dict(self):
        res = super()._base_body()
        res.update(
            {
                "spec": {
                    "selector": {"name": "internal-http"},
                    "ports": [
                        {"name": "rate-limit", "port": 82},
                        {"name": "http-auth", "port": 81},
                        {"name": "http-no-auth", "port": 80},
                        {"name": "https", "port": 443},
                    ],
                }
            }
        )
        return res
