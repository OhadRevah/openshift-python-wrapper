# -*- coding: utf-8 -*-

import logging

from .resource import NamespacedResource


LOGGER = logging.getLogger(__name__)


class PersistentVolumeClaim(NamespacedResource):
    """
    PersistentVolumeClaim object
    """

    api_version = 'v1'

    def bound(self):
        """
        Check if PVC is bound

        Returns:
            bool: True if bound else False
        """
        LOGGER.info(f"Check if {self.kind} {self.name} is bound")
        return self.status == 'Bound'
