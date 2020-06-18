import http
import logging

import pytest
import requests
import yaml
from providers.rhv import rhv
from pytest_testconfig import config as py_config
from resources.secret import Secret
from resources.virtual_machine_import import VirtualMachineImport
from tests.vmimport.rhv import utils
from utilities.virt import create_vm_import


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def rhv_provider():
    return rhv.RHV(
        url=py_config["rhv_url"],
        username=py_config["rhv_username"],
        password=py_config["rhv_password"],
    )


@pytest.fixture(scope="module")
def ovirt_config():
    api_url = py_config["rhv_url"]
    username = py_config["rhv_username"]
    password = py_config["rhv_password"]

    with requests.get(
        f"{api_url}/vms", auth=(username, password), verify=False
    ) as response:
        if response.status_code != http.HTTPStatus.OK:
            pytest.skip(
                msg=f"Skipping VM import tests: oVirt {api_url} is not available."
            )

    return {
        "apiUrl": api_url,
        "username": username,
        "password": password,
        "caCert": py_config["rhv_cert"],
    }


@pytest.fixture(scope="module")
def secret(namespace, ovirt_config):
    with Secret(
        name="ovirt-secret",
        namespace=namespace.name,
        string_data={"ovirt": yaml.dump(ovirt_config)},
    ) as secret:
        yield secret


@pytest.mark.polarion("CNV-4381")
def test_vm_import(secret, namespace, rhv_provider):
    source_vm_name = "cirros-vm-for-tests"
    source_vm_cluster = "iscsi"
    target_vm_name = "test"
    with create_vm_import(
        name="import-vm-by-id",
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=source_vm_name,
        cluster_name=source_vm_cluster,
        target_vm_name=target_vm_name,
        start_vm=True,
        ovirt_mappings=utils.POD_MAPPING,
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_RUNNING
        )
        vm = vmimport.vm
        assert vm.exists
        assert vm.instance["metadata"]["name"] == target_vm_name
        check_vm_config(
            vm=vm.instance,
            rhv_provider=rhv_provider,
            source_vm_name=source_vm_name,
            source_vm_cluster=source_vm_cluster,
        )


def check_vm_config(vm, rhv_provider, source_vm_name, source_vm_cluster):
    vms_service = rhv_provider.api.system_service().vms_service()
    source_vm = vms_service.list(
        search=f"name={source_vm_name} cluster={source_vm_cluster}"
    )[0]
    source_vm_nic = vms_service.vm_service(source_vm.id).nics_service().list()[0]

    spec = vm.spec.template.spec

    domain = spec.domain
    interfaces = domain.devices.interfaces

    cpu = domain.cpu
    assert cpu.cores == 1
    assert cpu.sockets == 1
    assert cpu.threads == 1

    assert domain.firmware.bootloader.bios
    assert domain.machine.type == "q35"

    assert len(interfaces) == 1
    assert interfaces[0].macAddress == source_vm_nic.mac.address

    assert len(spec.volumes) == 1
