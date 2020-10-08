# -*- coding: utf-8 -*-

"""
Pytest conftest file for VM Import tests
"""

import logging
from subprocess import STDOUT, check_output

import pytest
import utilities.network
import yaml
from providers.rhv import rhv
from resources.secret import Secret
from resources.virtual_machine_import import ResourceMapping
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
def cert_file(tmpdir_factory, provider_data):
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

    if provider_data["type"] == "rhv":
        with rhv.RHV(
            url=provider_data["api_url"],
            username=provider_data["username"],
            password=provider_data["password"],
            ca_file=cert_file,
        ) as provider:
            if not provider.api.test():
                pytest.skip(
                    msg=f"Skipping VM import tests: oVirt {provider.url} is not available."
                )
            yield provider
    else:
        yield


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
