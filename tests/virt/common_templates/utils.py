# -*- coding: utf-8 -*-


from pytest_testconfig import config as py_config

from resources.datavolume import ImportFromHttpDataVolume
from resources.virtual_machine import VirtualMachine


class VirtualMachineFromTemplate(VirtualMachine):
    def __init__(self, name, namespace, body):
        super().__init__(name=name, namespace=namespace)
        self.body = body

    def _to_dict(self):
        return self.body


class DataVolumeTestResource(ImportFromHttpDataVolume):
    def __init__(
        self,
        name,
        namespace,
        url,
        os_release,
        template_name,
        size="25Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
    ):
        super().__init__(name, namespace, size, storage_class, url, content_type)
        self.os_release = os_release
        self.template_name = template_name
