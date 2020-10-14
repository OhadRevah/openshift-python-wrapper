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
from tests.vmimport.utils import ProviderMappings


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
    if provider_data["type"] == "rhv":
        cert = check_output(
            [
                "/bin/sh",
                "-c",
                f"openssl s_client -connect {provider_data['fqdn']}:443 -showcerts < /dev/null",
            ],
            stderr=STDOUT,
        )
        cert_file = tmpdir_factory.mktemp("RHV").join("rhe_cert.crt")
        cert_file.write(cert)
        return cert_file.strpath


@pytest.fixture(scope="module")
def provider(provider_data, cert_file):
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


@pytest.fixture(scope="module")
def secret(provider_data, namespace, provider):
    string_data = {
        "apiUrl": provider.url,
        "username": provider.username,
        "password": provider.password,
        "caCert": open(provider.ca_file, "r").read(),
    }
    if provider_data["type"] == "rhv":
        with Secret(
            name="ovirt-secret",
            namespace=namespace.name,
            string_data={"ovirt": yaml.dump(string_data)},
        ) as secret:
            yield secret


@pytest.fixture(scope="module")
def resource_mapping(request, namespace):
    with ResourceMapping(
        name="resource-mapping",
        namespace=namespace.name,
        mapping={
            "ovirt": ProviderMappings(
                network_mappings=[utils.POD_MAPPING],
                storage_mappings=utils.storage_mapping_by_source_vm_disks_storage_name(
                    storage_classes=["nfs", "local-block", "hostpath-provisioner"],
                    source_volumes_config=request.param,
                ),
            )
        },
    ) as resource_mapping:
        yield resource_mapping
