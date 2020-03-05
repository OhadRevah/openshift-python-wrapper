# -*- coding: utf-8 -*-

import logging

import pytest
import tests.network.utils as network_utils
from pytest_testconfig import config as py_config
from resources.service_account import ServiceAccount
from resources.template import Template
from resources.utils import TimeoutSampler
from tests.compute.ssp.supported_os.common_templates.utils import (
    enable_ssh_service_in_vm,
)
from tests.compute.utils import WinRMcliPod, nmcli_add_con_cmds
from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    RHEL_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)

"""
RHEL7 fixtures and network configuration
"""


@pytest.fixture(scope="class")
def rhel7_psi_network_config():
    """ RHEL7 network configuration for PSI clusters """

    return {
        "vm_address": "172.16.0.90",
        "helper_vm_address": "172.16.0.91",
        "subnet": "172.16.0.0",
        "default_gw": "172.16.0.1",
        "dns_server": "172.16.0.16",
    }


@pytest.fixture(scope="class")
def network_attachment_definition(
    skip_ceph_on_rhel7, rhel7_ovs_bridge, namespace, rhel7_workers
):
    if rhel7_workers:
        with network_utils.bridge_nad(
            nad_type=network_utils.OVS,
            nad_name="rhel7-nad",
            bridge_name=rhel7_ovs_bridge,
            namespace=namespace,
        ) as network_attachment_definition:
            yield network_attachment_definition
    else:
        yield


@pytest.fixture(scope="class")
def network_configuration(
    skip_ceph_on_rhel7, rhel7_workers, network_attachment_definition,
):
    if rhel7_workers:
        return {network_attachment_definition.name: network_attachment_definition.name}


@pytest.fixture(scope="class")
def cloud_init_data(
    request, skip_ceph_on_rhel7, rhel7_workers, rhel7_psi_network_config,
):
    if rhel7_workers:
        bootcmds = nmcli_add_con_cmds(
            iface="eth1",
            ip=rhel7_psi_network_config["vm_address"],
            default_gw=rhel7_psi_network_config["default_gw"],
            dns_server=rhel7_psi_network_config["dns_server"],
        )

        cloud_init_data = (
            RHEL_CLOUD_INIT_PASSWORD
            if "rhel" in request.fspath.strpath
            else FEDORA_CLOUD_INIT_PASSWORD
        )
        cloud_init_data["bootcmd"] = bootcmds

        return cloud_init_data


@pytest.fixture(scope="class")
def bridge_attached_helper_vm(
    skip_ceph_on_rhel7,
    rhel7_workers,
    schedulable_nodes,
    namespace,
    unprivileged_client,
    network_attachment_definition,
    rhel7_psi_network_config,
):
    if rhel7_workers:
        name = "helper-vm"
        networks = {
            network_attachment_definition.name: network_attachment_definition.name
        }

        bootcmds = nmcli_add_con_cmds(
            iface="eth1",
            ip=rhel7_psi_network_config["helper_vm_address"],
            default_gw=rhel7_psi_network_config["default_gw"],
            dns_server=rhel7_psi_network_config["dns_server"],
        )

        cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
        cloud_init_data["bootcmd"] = bootcmds

        # On PSI, set DHCP server configuration
        if not py_config["bare_metal_cluster"]:
            cloud_init_data["runcmd"] = [
                "sh -c \"echo $'default-lease-time 3600;\\nmax-lease-time 7200;"
                f"\\nauthoritative;\\nsubnet {rhel7_psi_network_config['subnet']} "
                "netmask 255.255.255.0 {"
                "\\noption subnet-mask 255.255.255.0;\\nrange  "
                f"{rhel7_psi_network_config['vm_address']} {rhel7_psi_network_config['vm_address']};"
                f"\\noption routers {rhel7_psi_network_config['default_gw']};\\n"
                f"option domain-name-servers {rhel7_psi_network_config['dns_server']};"
                "\\n}' > /etc/dhcp/dhcpd.conf\"",
                "sysctl net.ipv4.icmp_echo_ignore_broadcasts=0",
                "sudo systemctl enable dhcpd",
                "sudo systemctl restart dhcpd",
            ]

        with VirtualMachineForTests(
            namespace=namespace.name,
            name=name,
            body=fedora_vm_body(name),
            networks=networks,
            interfaces=sorted(networks.keys()),
            node_selector=schedulable_nodes[0].name,
            cloud_init_data=cloud_init_data,
            client=unprivileged_client,
        ) as vm:
            vm.start(wait=True)
            wait_for_vm_interfaces(vm.vmi)
            enable_ssh_service_in_vm(vm=vm, console_impl=console.Fedora)
            yield vm
    else:
        yield


"""
General tests fixtures
"""


def vm_instance_from_template(
    request,
    unprivileged_client,
    namespace,
    data_volume,
    network_configuration,
    cloud_init_data,
):
    """ Create a VM from template and start it (start step could be skipped by setting
    request.param['start_vm'] to False.

    The call to this function is triggered by calling either
    vm_instance_from_template_scope_function or vm_instance_from_template_scope_class.

    Prerequisite - a DV must be created prior to VM creation.
    """

    with VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"].replace(".", "-").lower(),
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**request.param["template_labels"]),
        template_dv=data_volume,
        vm_dict=request.param.get("vm_dict"),
        cpu_threads=request.param.get("cpu_threads"),
        network_model=request.param.get("network_model"),
        network_multiqueue=request.param.get("network_multiqueue"),
        networks=network_configuration if network_configuration else None,
        interfaces=sorted(network_configuration.keys())
        if network_configuration
        else None,
        cloud_init_data=cloud_init_data if cloud_init_data else None,
    ) as vm:
        if request.param.get("start_vm", True):
            vm.start(wait=True)
            vm.vmi.wait_until_running()
            if request.param.get("guest_agent", True):
                wait_for_vm_interfaces(vm.vmi)
        yield vm


@pytest.fixture()
def vm_instance_from_template_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    network_configuration,
    cloud_init_data,
):
    """ Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    yield from vm_instance_from_template(
        request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )


@pytest.fixture(scope="class")
def vm_instance_from_template_scope_class(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_class,
    network_configuration,
    cloud_init_data,
):
    """ Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    yield from vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    )


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


"""
Windows-specific fixtures
"""


@pytest.fixture(scope="module")
def sa_ready(namespace):
    #  Wait for 'default' service account secrets to be exists.
    #  The Pod creating will fail if we try to create it before.
    default_sa = ServiceAccount(name="default", namespace=namespace.name)
    sampler = TimeoutSampler(
        timeout=10, sleep=1, func=lambda: default_sa.instance.secrets
    )
    for sample in sampler:
        if sample:
            return


def winrmcli_pod(namespace, sa_ready):
    """ Deploy winrm-cli Pod into the same namespace.

    The call to this function is triggered by calling either
    winrmcli_pod_scope_module or winrmcli_pod_scope_class.
    """

    with WinRMcliPod(name="winrmcli-pod", namespace=namespace.name) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=90)
        yield pod


@pytest.fixture()
def winrmcli_pod_scope_function(rhel7_workers, namespace, sa_ready):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(namespace=namespace, sa_ready=sa_ready)


@pytest.fixture(scope="module")
def winrmcli_pod_scope_module(rhel7_workers, namespace, sa_ready):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(namespace=namespace, sa_ready=sa_ready)


@pytest.fixture(scope="class")
def winrmcli_pod_scope_class(rhel7_workers, namespace, sa_ready):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(namespace=namespace, sa_ready=sa_ready)
