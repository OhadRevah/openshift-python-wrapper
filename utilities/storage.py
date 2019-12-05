from contextlib import contextmanager

from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume


class DataVolumeTestResource(DataVolume):
    def __init__(
        self,
        name,
        namespace,
        url,
        os_release=None,
        template_labels=None,
        size="25Gi",
        storage_class=None,
        content_type=DataVolume.ContentType.KUBEVIRT,
        access_modes=DataVolume.AccessMode.RWO,
        volume_mode=None,
    ):
        storage_class = storage_class or py_config["default_storage_class"]
        super().__init__(
            source="http",
            name=name,
            namespace=namespace,
            size=size,
            storage_class=storage_class,
            url=url,
            content_type=content_type,
            access_modes=access_modes,
            volume_mode=volume_mode,
        )
        self.os_release = os_release
        self.template_labels = template_labels


@contextmanager
def create_dv(
    dv_name,
    namespace,
    storage_class,
    url=None,
    source="http",
    content_type=DataVolume.ContentType.KUBEVIRT,
    size="5Gi",
    secret=None,
    cert_configmap=None,
    volume_mode=DataVolume.VolumeMode.FILE,
    hostpath_node=None,
):
    with DataVolume(
        source=source,
        name=dv_name,
        namespace=namespace,
        url=url,
        content_type=content_type,
        size=size,
        storage_class=storage_class,
        cert_configmap=cert_configmap,
        volume_mode=volume_mode,
        hostpath_node=hostpath_node,
        secret={"secret": secret} if secret else {},
    ) as dv:
        yield dv
