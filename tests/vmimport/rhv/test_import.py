import logging

import pytest
import yaml
from providers.rhv import rhv
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.secret import Secret
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_import import VirtualMachineImport
from tests.vmimport.rhv import utils
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import create_vm_import


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def rhv_provider():
    with rhv.RHV(
        url=py_config["rhv_url"],
        username=py_config["rhv_username"],
        password=py_config["rhv_password"],
    ) as provider:
        if not provider.api.test():
            pytest.skip(
                msg=f"Skipping VM import tests: oVirt {provider.url} is not available."
            )
        yield provider


@pytest.fixture(scope="module")
def secret(namespace, rhv_provider):
    string_data = {
        "apiUrl": rhv_provider.url,
        "username": rhv_provider.username,
        "password": rhv_provider.password,
        "caCert": open(rhv_provider.ca_file, "r").read(),
    }
    with Secret(
        name="ovirt-secret",
        namespace=namespace.name,
        string_data={"ovirt": yaml.dump(string_data)},
    ) as secret:
        yield secret


@pytest.mark.bugzilla(
    1849664, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-4381")
def test_vm_import(secret, namespace, rhv_provider):
    source_vm_name = "cirros-vm-for-tests"
    source_vm_cluster = "iscsi"
    target_vm_name = "test"
    with create_vm_import(
        name="import-vm-by-name",
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


@pytest.mark.polarion("CNV-4392")
def test_vm_import_cancelation(secret, namespace, rhv_provider, default_client):
    import_name = "import-vm-cancel"
    source_vm_name = "cirros-vm-no-nics"
    source_vm_cluster = "iscsi"
    target_vm_name = "test-cancel"
    with create_vm_import(
        name=import_name,
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=source_vm_name,
        cluster_name=source_vm_cluster,
        target_vm_name=target_vm_name,
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.ProcessingConditionReason.COPYING_DISKS,
            cond_type=VirtualMachineImport.Condition.PROCESSING,
        )
    # We need to use assert wait because it takes some time until the resources
    # are deleted.
    source_vm = rhv_provider.vm(name=source_vm_name, cluster=source_vm_cluster)
    vm_disk_id = rhv_provider.vm_disk_attachments(vm=source_vm)[0].id
    VirtualMachine(name=target_vm_name, namespace=namespace.name).wait_deleted()
    DataVolume(
        name=f"{import_name}-{vm_disk_id}", namespace=namespace.name
    ).wait_deleted()
    for resource in (Secret, ConfigMap):
        for resource_object in resource.get(
            dyn_client=default_client, label_selector=utils.make_labels(import_name)
        ):
            resource_object.wait_deleted()


def check_vm_config(vm, rhv_provider, source_vm_name, source_vm_cluster):
    source_vm = rhv_provider.vm(name=source_vm_name, cluster=source_vm_cluster)
    source_vm_nic = rhv_provider.vm_nics(vm=source_vm)[0]
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
