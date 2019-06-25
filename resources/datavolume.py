# -*- coding: utf-8 -*-

import logging

from .resource import NamespacedResource, TIMEOUT
from .persistent_volume_claim import PersistentVolumeClaim

LOGGER = logging.getLogger(__name__)


class DataVolume(NamespacedResource):
    """
    DataVolume object.
    """
    api_version = 'cdi.kubevirt.io/v1alpha1'

    class Status:
        SUCCEEDED = 'Succeeded'
        FAILED = 'Failed'

    class AccessMode:
        """
        AccessMode object.
        """
        RWO = "ReadWriteOnce"
        ROX = "ReadOnlyMany"
        RWX = "ReadWriteMany"

    class ContentType:
        """
        ContentType object
        """
        KUBEVIRT = "kubevirt"
        ARCHIVE = "archive"

    def wait_deleted(self, timeout=TIMEOUT):
        """
       Wait until DataVolume and the PVC created by it are deleted

        Args:
        timeout (int):  Time to wait for the DataVolume and PVC to be deleted.

        Returns:
        bool: True if DataVolume and its PVC are gone, False if timeout reached.
        """
        pvc = PersistentVolumeClaim(name=self.name, namespace=self.namespace)
        super().wait_deleted(timeout=timeout)
        return pvc.wait_deleted(timeout=timeout)


class ImportDataVolume(DataVolume):
    def __init__(
            self, name, namespace, source, url, content_type, size, storage_class,
            access_modes=DataVolume.AccessMode.RWO, cert_configmap=None, client=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self.source = source
        self.url = url
        self.cert_configmap = cert_configmap
        self.content_type = content_type
        self.size = size
        self.access_modes = access_modes
        self.storage_class = storage_class

    def _base_body(self):
        body = super()._base_body()
        body.update({
            "spec": {
                "source": {
                    self.source: {
                        "url": self.url,
                    }
                },
                "pvc": {
                    "accessModes": [
                        self.access_modes
                    ],
                    "resources": {
                        "requests": {
                            "storage": self.size,
                        }
                    },
                },
            }
        })
        if self.content_type:
            body["spec"]["contentType"] = self.content_type
        if self.cert_configmap:
            body["spec"]["source"][self.source]["certConfigMap"] = self.cert_configmap
        if self.storage_class:
            body["spec"]["pvc"]["storageClassName"] = self.storage_class
        return body


class ImportFromHttpDataVolume(ImportDataVolume):
    def __init__(self, name, namespace, url, content_type, size, storage_class, access_modes=DataVolume.AccessMode.RWO):
        super().__init__(
            name, namespace, "http", url, content_type, size, storage_class, access_modes)


class ImportFromRegistryDataVolume(ImportDataVolume):
    def __init__(self, name, namespace, url, content_type, size, storage_class,
                 access_modes=DataVolume.AccessMode.RWO, cert_configmap=None):
        super().__init__(
            name, namespace, "registry", url, content_type, size, storage_class, access_modes, cert_configmap)
