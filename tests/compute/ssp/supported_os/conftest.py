# -*- coding: utf-8 -*-

import pytest
from ocp_resources.service import Service
from ocp_resources.template import Template
from packaging import version

from tests.compute.ssp.supported_os.utils import get_linux_guest_agent_version
from tests.compute.utils import (
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
)
from utilities.storage import create_or_update_data_source, data_volume
from utilities.virt import VirtualMachineForTestsFromTemplate


@pytest.fixture(scope="class")
def golden_image_data_volume_multi_rhel_os_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    rhel_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=rhel_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_rhel_os_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_rhel_os_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_data_volume_multi_windows_os_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    windows_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=windows_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_windows_os_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_windows_os_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_data_volume_multi_fedora_os_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    fedora_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=fedora_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_fedora_os_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_fedora_os_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_fedora_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_data_volume_multi_centos_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    centos_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=centos_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_centos_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_centos_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_centos_multi_storage_scope_class,
    )


def vm_object_from_template(
    unprivileged_client,
    namespace,
    data_source_object,
    request=None,
    os_matrix=None,
):
    """Instantiate a VM object

    The call to this function is triggered by calling either
    golden_image_vm_object_from_template_multi_storage_scope_function or
    golden_image_vm_object_from_template_multi_storage_scope_class.
    """

    param_dict = request.param if request else {}
    rhel6 = False

    if os_matrix:
        os_matrix_key = [*os_matrix][0]
        vm_name = os_matrix_key
        labels = Template.generate_template_labels(
            **os_matrix[os_matrix_key]["template_labels"]
        )
        rhel6 = "rhel-6" in os_matrix_key
    else:
        vm_name = request.param["vm_name"].replace(".", "-").lower()
        labels = Template.generate_template_labels(**request.param["template_labels"])

    # RHEL 6 - default network does not work (used only in test_rhel_os_support)
    # https://bugzilla.redhat.com/show_bug.cgi?id=1794243
    network_model = "e1000" if rhel6 else param_dict.get("network_model")
    network_multiqueue = False if rhel6 else param_dict.get("network_multiqueue")

    return VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=data_source_object,
        labels=labels,
        vm_dict=param_dict.get("vm_dict"),
        cpu_threads=param_dict.get("cpu_threads"),
        memory_requests=param_dict.get("memory_requests"),
        network_model=network_model,
        network_multiqueue=network_multiqueue,
        ssh=param_dict.get("ssh", True),
        systemctl_support=not rhel6,
        disable_sha2_algorithms=rhel6,
    )


@pytest.fixture()
def golden_image_vm_object_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_function,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source_object=golden_image_data_source_multi_storage_scope_function,
    )


@pytest.fixture()
def golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_class,
):
    """VM is created with function scope whereas golden image DV is created with class scope. to be used when a number
    of tests (each creates its relevant VM) are gathered under a class and use the same golden image DV.
    """
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source_object=golden_image_data_source_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_storage_scope_class(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_class,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source_object=golden_image_data_source_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    rhel_os_matrix__class__,
    golden_image_data_source_multi_rhel_os_multi_storage_scope_class,
):
    return vm_object_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=rhel_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_rhel_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class(
    request,
    cluster_cpu_model_scope_class,
    unprivileged_client,
    namespace,
    windows_os_matrix__class__,
    golden_image_data_source_multi_windows_os_multi_storage_scope_class,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=windows_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_windows_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class(
    request,
    cluster_cpu_model_scope_class,
    unprivileged_client,
    namespace,
    fedora_os_matrix__class__,
    golden_image_data_source_multi_fedora_os_multi_storage_scope_class,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=fedora_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_fedora_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class(
    cluster_cpu_model_scope_class,
    unprivileged_client,
    namespace,
    centos_os_matrix__class__,
    golden_image_data_source_multi_centos_multi_storage_scope_class,
):
    return vm_object_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=centos_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_centos_multi_storage_scope_class,
    )


def vm_ssh_service(vm):
    """Manages (creation and deletion) of a service to enable SSH access to the VM

    The call to this function is triggered by calling either
    golden_image_vm_ssh_service_multi_storage_scope_function or
    """

    vm.ssh_enable()
    yield
    vm.ssh_service.delete(wait=True)


@pytest.fixture()
def golden_image_vm_ssh_service_multi_storage_scope_function(
    golden_image_vm_instance_from_template_multi_storage_scope_function,
):
    yield from vm_ssh_service(
        vm=golden_image_vm_instance_from_template_multi_storage_scope_function
    )


@pytest.fixture(scope="class")
def golden_image_vm_ssh_service_multi_rhel_os_scope_class(
    golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
):
    yield from vm_ssh_service(
        vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
    )


@pytest.fixture(scope="class")
def golden_image_vm_ssh_service_multi_fedora_os_scope_class(
    golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
):

    yield from vm_ssh_service(
        vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
    )


@pytest.fixture(scope="class")
def golden_image_vm_ssh_service_multi_windows_os_scope_class(
    golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
):
    yield from vm_ssh_service(
        vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
    )


@pytest.fixture(scope="class")
def golden_image_vm_ssh_service_multi_centos_scope_class(
    golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
):
    yield from vm_ssh_service(
        vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
    )


@pytest.fixture()
def exposed_vm_service_multi_storage_scope_function(
    request,
    vm_instance_from_template_multi_storage_scope_function,
    schedulable_node_ips,
):
    vm_instance_from_template_multi_storage_scope_function.custom_service_enable(
        service_name=request.param["service_name"],
        port=request.param["service_port"],
        service_type=Service.Type.NODE_PORT,
        service_ip=list(schedulable_node_ips.values())[0],
    )


@pytest.fixture()
def golden_image_exposed_vm_service_multi_storage_scope_function(
    request,
    golden_image_vm_instance_from_template_multi_storage_scope_function,
    schedulable_node_ips,
):
    golden_image_vm_instance_from_template_multi_storage_scope_function.custom_service_enable(
        service_name=request.param["service_name"],
        port=request.param["service_port"],
        service_type=Service.Type.NODE_PORT,
        service_ip=list(schedulable_node_ips.values())[0],
    )


@pytest.fixture()
def skip_guest_agent_on_rhel6(rhel_os_matrix__class__):
    if "rhel-6" in [*rhel_os_matrix__class__][0]:
        pytest.skip("RHEL6 does not have guest agent")


@pytest.fixture()
def skip_guest_agent_on_win12(windows_os_matrix__class__):
    if "win-12" in [*windows_os_matrix__class__][0]:
        pytest.skip("win-12 doesn't support powershell commands")


def skip_on_guest_agent_version(vm, ga_version):
    qemu_guest_agent_version = get_linux_guest_agent_version(ssh_exec=vm.ssh_exec)
    if version.parse(qemu_guest_agent_version.split()[0]) < version.parse(ga_version):
        pytest.skip("Skipping on guest agent version {qemu_guest_agent_version}")


@pytest.fixture()
def skip_guest_agent_on_rhel(
    golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
):
    skip_on_guest_agent_version(
        vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        ga_version="4.2.0",
    )


@pytest.fixture()
def skip_guest_agent_on_centos(
    golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
):
    skip_on_guest_agent_version(
        vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        ga_version="4.2.0",
    )


@pytest.fixture(scope="class")
def mspaint_process_in_windows_os(
    golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
):
    process_name = "mspaint.exe"
    return start_and_fetch_processid_on_windows_vm(
        vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        process_name=process_name,
    )


@pytest.fixture(scope="class")
def ping_process_in_fedora_os(
    golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
):
    process_name = "ping"
    return start_and_fetch_processid_on_linux_vm(
        vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        process_name=process_name,
        args="localhost",
    )


@pytest.fixture(scope="class")
def ping_process_in_rhel_os(
    golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
):
    process_name = "ping"
    return start_and_fetch_processid_on_linux_vm(
        vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        process_name=process_name,
        args="localhost",
    )


@pytest.fixture(scope="class")
def ping_process_in_centos_os(
    golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
):
    process_name = "ping"
    return start_and_fetch_processid_on_linux_vm(
        vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        process_name=process_name,
        args="localhost",
    )
