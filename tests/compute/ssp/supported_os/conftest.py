# -*- coding: utf-8 -*-

import pytest
from resources.template import Template
from utilities.virt import VirtualMachineForTestsFromTemplate


def vm_object_from_template(
    request,
    unprivileged_client,
    namespace,
    data_volume_object,
    network_configuration,
    cloud_init_data,
):
    """ Instantiate a VM object

    The call to this function is triggered by calling either
    vm_object_from_template_scope_function or vm_object_from_template_scope_class.
    """

    return VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"].replace(".", "-").lower(),
        namespace=namespace.name,
        client=unprivileged_client,
        template_dv=data_volume_object,
        labels=Template.generate_template_labels(**request.param["template_labels"]),
        vm_dict=request.param.get("vm_dict"),
        cpu_threads=request.param.get("cpu_threads"),
        network_model=request.param.get("network_model"),
        network_multiqueue=request.param.get("network_multiqueue"),
        networks=network_configuration if network_configuration else None,
        interfaces=sorted(network_configuration.keys())
        if network_configuration
        else None,
        cloud_init_data=cloud_init_data if cloud_init_data else None,
    )


@pytest.fixture()
def vm_object_from_template_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    network_configuration,
    cloud_init_data,
):
    return vm_object_from_template(
        request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_object=data_volume_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )


@pytest.fixture(scope="class")
def vm_object_from_template_scope_class(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_class,
    network_configuration,
    cloud_init_data,
):
    return vm_object_from_template(
        request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_object=data_volume_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )
