# -*- coding: utf-8 -*-

from resources.virtual_machine import VirtualMachine
from utilities import console


CLOUD_INIT_USER_DATA = r"""
            #!/bin/sh
            echo 'printed from cloud-init userdata'"""


class VirtualMachineWithDV(VirtualMachine):
    def __init__(self, name, namespace, dv_name, cloud_init_data, client=None):
        super().__init__(name=name, namespace=namespace, client=client)
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


def create_vm_with_dv(dv):
    with VirtualMachineWithDV(name='cirros-vm', namespace=dv.namespace, dv_name=dv.name,
                              cloud_init_data=CLOUD_INIT_USER_DATA) as vm:
        assert vm.start()
        assert vm.vmi.wait_until_running()
        with console.Cirros(vm=vm.name, namespace=dv.namespace) as vm_console:
            vm_console.sendline("lsblk | grep disk | wc -l")
            vm_console.expect("2", timeout=60)
