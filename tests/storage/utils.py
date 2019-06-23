# -*- coding: utf-8 -*-

from resources.virtual_machine import VirtualMachine


class VirtualMachineWithDV(VirtualMachine):
    def __init__(self, name, namespace, dv_name, cloud_init_data):
        super().__init__(name, namespace)
        self._dv_name = dv_name
        self._cloud_init_data = cloud_init_data

    def _to_dict(self):
        res = super()._to_dict()

        spec = res["spec"]["template"]["spec"]
        spec["domain"]["devices"]["disks"] = [{
            "disk": {
                "bus": "virtio",
            },
            "name": "dv-disk",
        }, {
            "disk": {
                "bus": "virtio",
            },
            "name": "cloudinitdisk",
        }]

        spec["volumes"] = [{
            "name": "cloudinitdisk",
            "cloudInitNoCloud": {
                "userData": self._cloud_init_data,
            },
        }, {
            "name": "dv-disk",
            "dataVolume": {
                "name": self._dv_name,
            },
        }]
        return res
