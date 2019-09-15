# -*- coding: utf-8 -*-
import logging

from .resource import NamespacedResource


LOGGER = logging.getLogger(__name__)


class Route(NamespacedResource):
    """
    OpenShift Route object.
    """

    api_group = "route.openshift.io"

    def __init__(self, name, namespace, service=None):
        super().__init__(name=name, namespace=namespace)
        self.service = service

    def _to_dict(self):
        body = super()._base_body()
        if self.service:
            body.update({"spec": {"to": {"kind": "Service", "name": self.service}}})
        return body

    @property
    def exposed_service(self):
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
