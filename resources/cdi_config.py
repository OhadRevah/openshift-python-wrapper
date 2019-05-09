# -*- coding: utf-8 -*-

import logging

from .resource import Resource

LOGGER = logging.getLogger(__name__)


class CDIConfig(Resource):
    """
    CDIConfig object.
    """
    api_version = 'cdi.kubevirt.io/v1alpha1'

    @property
    def upload_proxy_url(self):
        return self.instance.status.uploadproxyurl
