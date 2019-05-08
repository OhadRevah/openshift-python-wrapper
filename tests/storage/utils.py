# -*- coding: utf-8 -*-

from resources.datavolume import DataVolume
from utilities import utils


def create_dv_from_template(dyn_client, template, **kwargs):
    """
    Create DataVolume from template
    Args:
        dyn_client (DynamicClient): client to interact with OpenShift
        template (string): path to DataVolume template
        kwargs(dict): a dictionary containing all arguments values in template

    Returns:
        DataVolume created from yaml
    """
    assert 'name' in kwargs.keys() and 'namespace' in kwargs.keys()
    dv = DataVolume(name=kwargs['name'], namespace=kwargs['namespace'])
    json_out = utils.generate_yaml_from_template(file_=template, **kwargs)
    assert dv.create_from_dict(
        dyn_client=dyn_client, resource_dict=json_out
    )
    return dv
