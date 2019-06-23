# -*- coding: utf-8 -*-

import logging

from .resource import Resource

LOGGER = logging.getLogger(__name__)


class UploadProxyURLError(Exception):
    def __init__(self, current_url, desired_url):
        self.current_url = current_url
        self.desired_url = desired_url

    def __str__(self):
        return f"Upload Proxy URL {self.current_url} does not match {self.desired_url}"


class CDIConfig(Resource):
    """
    CDIConfig object.
    """

    api_version = "cdi.kubevirt.io/v1alpha1"

    @property
    def upload_proxy_url(self):
        return self.instance.status.uploadProxyURL

    def wait_until_upload_url_changed(self, uploadproxy_url, timeout=120):
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
        resources = self.api()
        for rsc in resources.watch(
            timeout=timeout, field_selector=f"metadata.name=={self.name}"
        ):
            status = rsc["raw_object"]["status"]
            current_url = status.get("uploadProxyURL")
            if current_url == uploadproxy_url:
                return True
        raise UploadProxyURLError(current_url=current_url, desired_url=uploadproxy_url)
