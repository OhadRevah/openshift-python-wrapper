# -*- coding: utf-8 -*-

"""
Pytest conftest file for VM Import tests
"""

import logging
from subprocess import STDOUT, check_output

import pytest
import utilities.network
import yaml
from providers import providers
from resources.secret import Secret
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_import import ResourceMapping
from tests.network.utils import network_device
from tests.vmimport import utils
from tests.vmimport.utils import ProviderMappings, ResourceMappingItem, Source


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def provider_data(provider_matrix__module__):
    provider_key = [*provider_matrix__module__][0]
    return provider_matrix__module__[provider_key]


@pytest.fixture(scope="module")
def bridge_network(namespace):
    with utilities.network.network_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name="mybridge",
        interface_name="br1test",
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def vm_import_bridge_device(
    utility_pods,
    schedulable_nodes,
    skip_if_no_multinic_nodes,
    nodes_available_nics,
    bridge_network,
):
    ports = [
        utilities.network.get_hosts_common_ports(
            nodes_available_nics=nodes_available_nics
        )[0]
    ]
    with network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name=f"{bridge_network.name}-nncp",
        interface_name=bridge_network.bridge_name,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=ports,
    ) as iface:
        yield iface


@pytest.fixture(scope="module")
def cert_file(tmpdir_factory, provider_data):
    cert = None
    provider_type = provider_data["type"]
    if provider_type == "ovirt":
        cert = check_output(
            [
                "/bin/sh",
                "-c",
                f"openssl s_client -connect {provider_data['fqdn']}:443 -showcerts < /dev/null",
            ],
            stderr=STDOUT,
        )
    if provider_type == "vmware":
        cert = provider_data["thumbprint"]

    cert_file = tmpdir_factory.mktemp(provider_type.upper()).join(
        f"{provider_type}_cert.crt"
    )
    cert_file.write(cert)
    return cert_file.strpath


@pytest.fixture(scope="module")
def provider(provider_data, cert_file):
    """currently, only rhv providers are supported"""
    """the tests can still run against vmware with some missing checks"""
    _provider = None
    _type = provider_data["type"]
    if _type == "ovirt":
        _provider = providers.RHV

    if _type == "vmware":
        # TODO: set 'provider = providers.VMWare' when VMWare implemented
        yield

    with _provider(
        url=provider_data["api_url"],
        username=provider_data["username"],
        password=provider_data["password"],
        ca_file=cert_file,
    ) as provider:
        if not provider.test:
            pytest.skip(
                msg=f"Skipping VM import tests: {_type} {provider.url} is not available."
            )
        yield provider


@pytest.fixture(scope="module")
def secret(provider_data, namespace, cert_file):
    secret_type = provider_data["type"]
    string_data = {
        "apiUrl": provider_data["api_url"],
        "username": provider_data["username"],
        "password": provider_data["password"],
        "caCert"
        if secret_type == "ovirt"
        else "thumbprint": open(cert_file, "r").read(),
    }
    with Secret(
        name=f"{secret_type}-secret",
        namespace=namespace.name,
        string_data={secret_type: yaml.dump(string_data)},
    ) as secret:
        yield secret


@pytest.fixture(scope="module")
def pod_network(provider_data):
    mapping = ResourceMappingItem(target_name="pod", target_type="pod")
    mapping.source_name = Source.default_network_names.get(provider_data["type"])[0]

    return mapping


@pytest.fixture(scope="module")
def multus_network(provider_data):
    mapping = ResourceMappingItem(target_name="mybridge", target_type="multus")
    mapping.source_name = Source.default_network_names.get(provider_data["type"])[1]

    return mapping


@pytest.fixture(scope="module")
def providers_mapping_network_only(request, pod_network, multus_network, provider_data):
    return utils.network_mappings(
        items=[pod_network, multus_network][
            : request.param if hasattr(request, "param") else 1
        ]
    )


@pytest.fixture(scope="module")
def resource_mapping(request, namespace, pod_network, provider_data):
    with ResourceMapping(
        name="resource-mapping",
        namespace=namespace.name,
        mapping={
            provider_data["type"]: ProviderMappings(
                network_mappings=[pod_network],
                storage_mappings=utils.storage_mapping_by_source_vm_disks_storage_name(
                    storage_classes=["nfs", "local-block", "hostpath-provisioner"],
                    source_volumes_config=request.param,
                ),
            )
        },
    ) as resource_mapping:
        yield resource_mapping


@pytest.fixture()
def no_vms_in_namespace(admin_client, namespace):
    yield
    for vm in VirtualMachine.get(dyn_client=admin_client, namespace=namespace.name):
        if vm.vmi.status == vm.vmi.Status.RUNNING:
            vm.stop(wait=True)
        vm.delete(wait=True)
