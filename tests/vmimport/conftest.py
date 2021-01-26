# -*- coding: utf-8 -*-

"""
Pytest conftest file for VM Import tests
"""

import logging
from subprocess import STDOUT, check_output

import pytest
import yaml
from pytest_testconfig import py_config
from resources.resource import ResourceEditor
from resources.secret import Secret
from resources.storage_class import StorageClass
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_import import ResourceMapping

import utilities.network
from providers import providers
from tests.vmimport import utils
from tests.vmimport.utils import ProviderMappings, ResourceMappingItem, Source
from utilities.network import network_device


LOGGER = logging.getLogger(__name__)


def vmware_provider(provider_data):
    return provider_data["type"] == "vmware"


def rhv_provider(provider_data):
    return provider_data["type"] == "ovirt"


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
    hosts_common_available_ports,
    bridge_network,
):
    with network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name=f"{bridge_network.name}-nncp",
        interface_name=bridge_network.bridge_name,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[hosts_common_available_ports[0]],
    ) as iface:
        yield iface


@pytest.fixture(scope="module")
def ca_cert(provider_data):
    if rhv_provider(provider_data):
        return check_output(
            [
                "/bin/sh",
                "-c",
                f"openssl s_client -connect {provider_data['fqdn']}:443 -showcerts < /dev/null",
            ],
            stderr=STDOUT,
        )


@pytest.fixture(scope="module")
def cert_file(tmpdir_factory, provider_data, ca_cert):
    if rhv_provider(provider_data):
        provider_type = provider_data["type"]
        if provider_type == "ovirt":
            cert_file = tmpdir_factory.mktemp(provider_type.upper()).join(
                f"{provider_type}_cert.crt"
            )
            cert_file.write(ca_cert)
            return cert_file.strpath


@pytest.fixture(scope="module")
def thumbprint(provider_data):
    if vmware_provider(provider_data):
        return check_output(
            [
                "/bin/sh",
                "-c",
                f"openssl s_client -connect {provider_data['fqdn']}:443 </dev/null 2>/dev/null | openssl x509 "
                f"-fingerprint -noout -in /dev/stdin | cut -d '=' -f 2 | tr -d $'\n'",
            ],
            stderr=STDOUT,
        )


@pytest.fixture(scope="module")
def provider(provider_data, cert_file, thumbprint):
    """currently, only rhv providers are supported"""
    """the tests can still run against vmware with some missing checks"""
    _provider = None
    provider_args = {
        "username": provider_data["username"],
        "password": provider_data["password"],
    }

    if rhv_provider(provider_data):
        provider_args["host"] = provider_data["api_url"]
        provider_args["ca_file"] = cert_file
        _provider = providers.RHV

    if vmware_provider(provider_data):
        provider_args["host"] = provider_data["fqdn"]
        provider_args["thumbprint"] = provider_data["thumbprint"]
        _provider = providers.VMWare

    with _provider(**provider_args) as provider:
        if not provider.test:
            pytest.skip(
                msg=f"Skipping VM import tests: {provider_args['host']} is not available."
            )
        yield provider


@pytest.fixture(scope="module")
def secret(provider_data, namespace, ca_cert, thumbprint):
    provider_type = provider_data["type"]
    string_data = {
        "apiUrl": provider_data["api_url"],
        "username": provider_data["username"],
        "password": provider_data["password"],
    }
    if rhv_provider(provider_data):
        string_data["caCert"] = ca_cert

    if vmware_provider(provider_data):
        string_data["thumbprint"] = thumbprint

    with Secret(
        name=f"{provider_type}-secret",
        namespace=namespace.name,
        string_data={provider_type: yaml.dump(string_data)},
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
def skip_if_less_than_x_storage_classes(request):
    if len(py_config["storage_class_matrix"]) < request.param:
        pytest.skip(
            f"Destination OCP Must have at least {request.param} Storage Classes in order to run this test."
        )


@pytest.fixture(scope="module")
def resource_mapping(request, namespace, pod_network, provider_data):
    sc_names = [[*sc][0] for sc in py_config["storage_class_matrix"]]
    sc_names.insert(0, sc_names.pop(sc_names.index(py_config["default_storage_class"])))
    # The default storage class should be 1st so it is mapped to the 1st disk's datastore/domain

    with ResourceMapping(
        name="resource-mapping",
        namespace=namespace.name,
        mapping={
            provider_data["type"]: ProviderMappings(
                network_mappings=[pod_network],
                storage_mappings=utils.storage_mapping_by_source_vm_disks_storage_name(
                    storage_classes=sc_names,
                    source_volumes_config=Source.vms[
                        f"{request.param}-{provider_data['fqdn']}"
                    ]["volumes_details"],
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


@pytest.fixture()
def skip_if_vmware_provider(provider_data):
    if provider_data["type"] == "vmware":
        pytest.skip("skipping for vmware provider.")


@pytest.fixture()
def default_sc_multi_storage(
    admin_client,
    removed_default_storage_classes,
    storage_class_matrix__function__,
):
    sc_name = [*storage_class_matrix__function__][0]
    sc = list(StorageClass.get(dyn_client=admin_client, name=sc_name))
    with ResourceEditor(
        patches={
            sc[0]: {
                "metadata": {
                    "annotations": {StorageClass.Annotations.IS_DEFAULT_CLASS: "true"},
                    "name": sc_name,
                }
            }
        }
    ):
        yield sc
