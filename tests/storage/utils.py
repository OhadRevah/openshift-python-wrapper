# -*- coding: utf-8 -*-

from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.virtual_machine import VirtualMachine
from utilities import utils


def create_dv_from_template(template, **kwargs):
    """
    Create DataVolume from template
    Args:
        template (string): path to DataVolume template
        kwargs(dict): a dictionary containing all arguments values in template

    Returns:
        DataVolume created from yaml
    """
    assert 'name' in kwargs.keys() and 'namespace' in kwargs.keys()
    template_conf = py_config['storage_defaults']
    kwargs.update(template_conf)
    dv = DataVolume(name=kwargs['name'], namespace=kwargs['namespace'])
    json_out = utils.generate_yaml_from_template(file_=template, **kwargs)
    assert dv.create_from_dict(dyn_client=dv.client, data=json_out)
    return dv


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
