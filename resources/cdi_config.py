# -*- coding: utf-8 -*-

import logging

from urllib3.exceptions import ProtocolError

from resources.utils import TimeoutSampler
from .resource import Resource, TIMEOUT

LOGGER = logging.getLogger(__name__)


class CDIConfig(Resource):
    """
    CDIConfig object.
    """

    api_group = "cdi.kubevirt.io"

    @property
    def upload_proxy_url(self):
        return self.instance.status.uploadProxyURL

    def wait_until_upload_url_changed(self, uploadproxy_url, timeout=TIMEOUT):
        """
        Wait until upload proxy url is changed

        Args:
            timeout (int): Time to wait for CDI Config.

        Returns:
            bool: True if url is equal to uploadProxyURL.
        """
        LOGGER.info(
            f"Wait for {self.kind} {self.name} to ensure current URL == uploadProxyURL"
        )
        samples = TimeoutSampler(
            timeout=timeout,
            sleep=1,
            exceptions=ProtocolError,
            func=self.api().get,
            field_selector=f"metadata.name=={self.name}",
        )
        for sample in samples:
            if sample.items:
                status = sample.items[0].status
                current_url = status.uploadProxyURL
                if current_url == uploadproxy_url:
                    return
