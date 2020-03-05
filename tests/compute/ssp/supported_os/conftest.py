# -*- coding: utf-8 -*-

import pytest
from resources.template import Template
from utilities.storage import data_volume
from utilities.virt import VirtualMachineForTestsFromTemplate


@pytest.fixture(scope="class")
def data_volume_rhel_os(
    skip_ceph_on_rhel7,
    namespace,
    storage_class_matrix,
    schedulable_nodes,
    rhel_os_matrix,
):
    yield from data_volume(
        namespace=namespace,
        storage_class_matrix=storage_class_matrix,
        schedulable_nodes=schedulable_nodes,
        os_matrix=rhel_os_matrix,
    )


@pytest.fixture(scope="class")
def data_volume_windows_os(
    skip_ceph_on_rhel7,
    namespace,
    storage_class_matrix,
    schedulable_nodes,
    windows_os_matrix,
):
    yield from data_volume(
        namespace=namespace,
        storage_class_matrix=storage_class_matrix,
        schedulable_nodes=schedulable_nodes,
        os_matrix=windows_os_matrix,
    )


def vm_object_from_template(
    unprivileged_client,
    namespace,
    data_volume_object,
    network_configuration,
    cloud_init_data,
    request=None,
    os_matrix=None,
):
    """ Instantiate a VM object

    The call to this function is triggered by calling either
    vm_object_from_template_scope_function or vm_object_from_template_scope_class.
    """

    param_dict = request.param if request else {}
    if os_matrix:
        os_matrix_key = [*os_matrix][0]
        vm_name = os_matrix_key
        labels = Template.generate_template_labels(
            **os_matrix[os_matrix_key]["template_labels"]
        )
    else:
        vm_name = request.param["vm_name"].replace(".", "-").lower()
        labels = Template.generate_template_labels(**request.param["template_labels"])

    return VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        template_dv=data_volume_object,
        labels=labels,
        vm_dict=param_dict.get("vm_dict"),
        cpu_threads=param_dict.get("cpu_threads"),
        network_model=param_dict.get("network_model"),
        network_multiqueue=param_dict.get("network_multiqueue"),
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
        request=request,
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
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_object=data_volume_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )


@pytest.fixture(scope="class")
def vm_object_from_template_rhel_os(
    unprivileged_client,
    namespace,
    rhel_os_matrix,
    data_volume_rhel_os,
    network_configuration,
    cloud_init_data,
):
    return vm_object_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=rhel_os_matrix,
        data_volume_object=data_volume_rhel_os,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )


@pytest.fixture(scope="class")
def vm_object_from_template_windows_os(
    request,
    unprivileged_client,
    namespace,
    windows_os_matrix,
    data_volume_windows_os,
    network_configuration,
    cloud_init_data,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=windows_os_matrix,
        data_volume_object=data_volume_windows_os,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )


def vm_ssh_service(vm_object_from_template):
    """ Manages (creation and deletion) of a service to enable SSH access to the VM

    The call to this function is triggered by calling either
    vm_ssh_service_scope_function or
    vm_ssh_service_scope_class.
    """

    vm_object_from_template.ssh_enable()
    yield
    vm_object_from_template.ssh_service.delete(wait=True)


@pytest.fixture()
def vm_ssh_service_scope_function(
    rhel7_workers, vm_instance_from_template_scope_function
):
    # SSH expose service is not needed in RHEL7, VMs are accessed via brcnv
    if rhel7_workers:
        yield
    else:
        yield from vm_ssh_service(vm_instance_from_template_scope_function)


@pytest.fixture(scope="class")
def vm_ssh_service_scope_class(rhel7_workers, vm_object_from_template_scope_class):
    # SSH expose service is not needed in RHEL7, VMs are accessed via brcnv
    if rhel7_workers:
        yield
    else:
        yield from vm_ssh_service(vm_object_from_template_scope_class)


@pytest.fixture(scope="class")
def vm_ssh_service_rhel_os(rhel7_workers, vm_object_from_template_rhel_os):
    # SSH expose service is not needed in RHEL7, VMs are accessed via brcnv
    if rhel7_workers:
        yield
    else:
        yield from vm_ssh_service(vm_object_from_template_rhel_os)


@pytest.fixture()
def exposed_vm_service(request, vm_instance_from_template_scope_function):
    vm_instance_from_template_scope_function.custom_service_enable(
        service_name=request.param["service_name"], port=request.param["service_port"]
    )
