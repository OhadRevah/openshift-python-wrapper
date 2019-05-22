# -*- coding: utf-8 -*-

from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
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
