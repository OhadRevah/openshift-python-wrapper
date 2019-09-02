# -*- coding: utf-8 -*-

import logging

from .resource import NamespacedResource


LOGGER = logging.getLogger(__name__)


class PersistentVolumeClaim(NamespacedResource):
    """
    PersistentVolumeClaim object
    """

    api_version = "v1"

    class Status:
        BOUND = "Bound"

    def __init__(self, name, namespace, accessmodes=None, size=None):
        super().__init__(name=name, namespace=namespace)
        self.accessmodes = accessmodes
        self.size = size

    def _to_dict(self):
        res = super()._base_body()
        res.update(
            {
                "spec": {
                    "accessModes": [self.accessmodes],
                    "resources": {"requests": {"storage": self.size}},
                }
            }
        )
        return res

    def bound(self):
        """
        Check if PVC is bound

        Returns:
            bool: True if bound else False
        """
        LOGGER.info(f"Check if {self.kind} {self.name} is bound")
        return self.status == "Bound"
