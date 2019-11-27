from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromHttpDataVolume


class DataVolumeTestResource(ImportFromHttpDataVolume):
    def __init__(
        self,
        name,
        namespace,
        url,
        os_release=None,
        template_labels=None,
        size="25Gi",
        storage_class=None,
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
        access_modes=ImportFromHttpDataVolume.AccessMode.RWO,
        volume_mode=None,
    ):
        storage_class = storage_class or py_config["default_storage_class"]
        super().__init__(
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
