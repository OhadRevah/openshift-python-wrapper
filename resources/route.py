# -*- coding: utf-8 -*-
import logging

from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)


class Route(NamespacedResource):
    """
    OpenShift Route object.
    """
    api_version = 'route.openshift.io/v1'

    @property
    def service(self):
        """
        returns the service the route is exposing
        """
        return self.instance.spec.to.name

    @property
    def host(self):
        """
        returns hostname that is exposing the service
        """
        return self.instance.spec.host
