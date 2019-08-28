# -*- coding: utf-8 -*-

import logging

from .persistent_volume_claim import PersistentVolumeClaim
from .resource import TIMEOUT, NamespacedResource


LOGGER = logging.getLogger(__name__)


class DataVolume(NamespacedResource):
    """
    DataVolume object.
    """

    api_group = "cdi.kubevirt.io"

    class Status:
        SUCCEEDED = "Succeeded"
        FAILED = "Failed"
        IMPORT_SCHEDULED = "ImportScheduled"
        UPLOAD_READY = "UploadReady"

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

    class VolumeMode:
        """
        VolumeMode object
        """

        BLOCK = "Block"
        FILE = "File"

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

    def wait(self, timeout=600):
        self.wait_for_status(status=self.Status.SUCCEEDED, timeout=timeout)
        assert PersistentVolumeClaim(name=self.name, namespace=self.namespace).bound()


class DataVolumeTemplate(DataVolume):
    def __init__(
        self,
        name,
        namespace,
        source,
        size,
        storage_class,
        url=None,
        content_type=None,
        access_modes=DataVolume.AccessMode.RWO,
        cert_configmap=None,
        secret=None,
        client=None,
        volume_mode=None,
    ):
        super().__init__(name=name, namespace=namespace, client=client)
        self.source = source
        self.url = url
        self.cert_configmap = cert_configmap
        self.secret = secret
        self.content_type = content_type
        self.size = size
        self.access_modes = access_modes
        self.storage_class = storage_class
        self.volume_mode = volume_mode

    def _to_dict(self):
        res = super()._base_body()
        res.update(
            {
                "spec": {
                    "source": {self.source: {"url": self.url}},
                    "pvc": {
                        "accessModes": [self.access_modes],
                        "resources": {"requests": {"storage": self.size}},
                    },
                }
            }
        )
        if self.content_type:
            res["spec"]["contentType"] = self.content_type
        if self.cert_configmap:
            res["spec"]["source"][self.source]["certConfigMap"] = self.cert_configmap
        if self.storage_class:
            res["spec"]["pvc"]["storageClassName"] = self.storage_class
        if self.secret:
            res["spec"]["source"][self.source]["secretRef"] = self.secret
        if self.volume_mode:
            res["spec"]["pvc"]["volumeMode"] = self.volume_mode
        if self.source == "http" or "registry":
            res["spec"]["source"][self.source]["url"] = self.url
        elif self.source == "upload":
            res["spec"]["source"][self.source] = {}
        return res


class ImportFromHttpDataVolume(DataVolumeTemplate):
    def __init__(
        self,
        name,
        namespace,
        size,
        storage_class,
        url,
        content_type,
        access_modes=DataVolume.AccessMode.RWO,
        cert_configmap=None,
        secret=None,
        volume_mode=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            source="http",
            size=size,
            storage_class=storage_class,
            url=url,
            content_type=content_type,
            access_modes=access_modes,
            cert_configmap=cert_configmap,
            secret=secret,
            volume_mode=volume_mode,
        )


class ImportFromRegistryDataVolume(DataVolumeTemplate):
    def __init__(
        self,
        name,
        namespace,
        size,
        storage_class,
        url,
        content_type,
        access_modes=DataVolume.AccessMode.RWO,
        cert_configmap=None,
        volume_mode=None,
    ):
        super().__init__(
            name,
            namespace,
            "registry",
            size,
            storage_class,
            url,
            content_type,
            access_modes,
            cert_configmap,
            volume_mode,
        )


class UploadDataVolume(DataVolumeTemplate):
    def __init__(self, name, namespace, size, storage_class):
        super().__init__(name, namespace, "upload", size, storage_class)
