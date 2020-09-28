import logging
from subprocess import STDOUT, check_output

import ovirtsdk4.types
import pytest
import utilities.network
import yaml
from providers.rhv import rhv
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.secret import Secret
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_import import VirtualMachineImport
from tests.vmimport import utils
from utilities.virt import create_vm_import

from .utils import ResourceMappingItem, Source


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def source_cluster_name():
    return py_config["source_cluster_name"]


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
def rhv_cert_file(tmpdir_factory):
    cert = check_output(
        [
            "/bin/sh",
            "-c",
            f"openssl s_client -connect {py_config['rhv_fqdn']}:443 -showcerts < /dev/null",
        ],
        stderr=STDOUT,
    )
    cert_file = tmpdir_factory.mktemp("RHV").join("rhe_cert.crt")
    cert_file.write(cert)
    return cert_file.strpath


@pytest.fixture(scope="module")
def rhv_provider(rhv_cert_file):
    with rhv.RHV(
        url=py_config["rhv_api_url"],
        username=py_config["rhv_username"],
        password=py_config["rhv_password"],
        ca_file=rhv_cert_file,
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


def check_source_vm_status(rhv_provider, source_vm_name, source_vm_cluster, state):
    samples = TimeoutSampler(
        timeout=600,
        sleep=1,
        func=rhv_provider.vm,
        name=source_vm_name,
        cluster=source_vm_cluster,
    )
    for sample in samples:
        if sample.status == state:
            break


def import_name(vm_name):
    return f"{vm_name}-import"


def check_cnv_vm_network_config(
    vm, rhv_provider, source_vm_name, source_vm_cluster, expected_vm_config
):
    cnv_vm_network_interfaces = vm.instance.spec.template.spec.domain.devices.interfaces
    number_of_cnv_vm_network_interfaces = (
        len(cnv_vm_network_interfaces) if cnv_vm_network_interfaces is not None else 0
    )

    assert (
        number_of_cnv_vm_network_interfaces == expected_vm_config["network_interfaces"]
    ), "Wrong number of network interfaces"

    failed_assert_msgs = []
    for nic_index, source_vm_nic in enumerate(
        rhv_provider.vm_nics(
            vm=rhv_provider.vm(name=source_vm_name, cluster=source_vm_cluster)
        )
    ):
        cnv_vm_mac = cnv_vm_network_interfaces[nic_index].macAddress
        source_vm_mac = source_vm_nic.mac.address
        if cnv_vm_mac != source_vm_mac:
            failed_assert_msgs.append(
                f"mac address for nic {source_vm_nic.name} check failed, Expected:{source_vm_mac}, Actual: {cnv_vm_mac}"
            )

    assert not failed_assert_msgs, f"Failed verifications: {failed_assert_msgs}"


def check_cnv_vm_cpu_config(vm, expected_vm_config):

    machine = vm.instance.spec.template.spec.domain.machine
    cpu = vm.instance.spec.template.spec.domain.cpu

    failed_assert_msgs = []
    for check, value in zip(
        ["cpu_cores", "cpu_sockets", "cpu_threads", "machine_type"],
        [cpu.cores, cpu.sockets, cpu.threads, machine.type],
    ):
        if value != expected_vm_config[check]:
            failed_assert_msgs.append(
                f"vm {check} check failed, Expected: {expected_vm_config[check]}, Actual: {value}"
            )

    assert not failed_assert_msgs, f"Failed verifications: {failed_assert_msgs}"


def check_cnv_vm_data_volumes(vm, expected_vm_config):
    cnv_vm_number_of_vol = (
        len(vm.instance.spec.template.spec.volumes)
        if vm.instance.spec.template.spec.volumes is not None
        else 0
    )
    assert (
        cnv_vm_number_of_vol == expected_vm_config["volumes"]
    ), "wrong number of data volumes"


def check_cnv_vm_config(
    vm,
    rhv_provider,
    source_vm_name,
    source_vm_cluster,
    expected_vm_config,
):
    assert vm.exists, f"vm {source_vm_name} does not exist."

    assert (
        vm.instance.metadata.name == expected_vm_config["name"]
    ), "vm name check failed"

    check_cnv_vm_cpu_config(vm=vm, expected_vm_config=expected_vm_config)

    check_cnv_vm_network_config(
        vm=vm,
        rhv_provider=rhv_provider,
        source_vm_name=source_vm_name,
        expected_vm_config=expected_vm_config,
        source_vm_cluster=source_vm_cluster,
    )

    check_cnv_vm_data_volumes(vm=vm, expected_vm_config=expected_vm_config)

    assert (
        vm.instance.spec.template.spec.domain.firmware.bootloader.bios
    ), "vm bootloader_bios check failed"


@pytest.mark.parametrize(
    "vm_key",
    [
        pytest.param(
            "cirros",
            marks=(pytest.mark.polarion("CNV-4381")),
        ),
        pytest.param(
            "vm63chars",
            marks=(pytest.mark.polarion("CNV-4592")),
        ),
    ],
)
def test_vm_import(secret, namespace, rhv_provider, source_cluster_name, vm_key):
    vm_config = Source.vms[vm_key]
    vm_name = vm_config["name"]

    with create_vm_import(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=source_cluster_name,
        target_vm_name=vm_name,
        start_vm=True,
        ovirt_mappings=utils.network_mappings(items=[utils.POD_MAPPING]),
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_RUNNING
        )
        check_cnv_vm_config(
            vm=vmimport.vm,
            rhv_provider=rhv_provider,
            source_vm_name=vm_name,
            source_vm_cluster=source_cluster_name,
            expected_vm_config=vm_config,
        )


@pytest.mark.polarion("CNV-4392")
def test_cancel_vm_import(
    secret, namespace, rhv_provider, admin_client, source_cluster_name
):
    vm_name = Source.vms["cirros-no-nics"]["name"]
    with create_vm_import(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=source_cluster_name,
        target_vm_name=vm_name,
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.ProcessingConditionReason.COPYING_DISKS,
            cond_type=VirtualMachineImport.Condition.PROCESSING,
        )
    # We need to use assert wait because it takes some time until the resources
    # are deleted.
    source_vm = rhv_provider.vm(name=vm_name, cluster=source_cluster_name)
    vm_disk_id = rhv_provider.vm_disk_attachments(vm=source_vm)[0].id
    VirtualMachine(name=vm_name, namespace=namespace.name).wait_deleted()
    DataVolume(
        name=f"{import_name(vm_name=vm_name)}-{vm_disk_id}",
        namespace=namespace.name,
    ).wait_deleted()
    for resource in (Secret, ConfigMap):
        for resource_object in resource.get(
            dyn_client=admin_client,
            label_selector=utils.make_labels(import_name(vm_name=vm_name)),
        ):
            resource_object.wait_deleted()


@pytest.mark.polarion("CNV-4391")
def test_running_vm_import(
    admin_client, namespace, rhv_provider, secret, source_cluster_name
):
    vm_name = Source.vms["cirros-running"]["name"]
    with create_vm_import(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=source_cluster_name,
        target_vm_name=vm_name,
        start_vm=True,
        ovirt_mappings=utils.network_mappings(items=[utils.POD_MAPPING]),
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_RUNNING,
        )
        check_source_vm_status(
            rhv_provider=rhv_provider,
            source_vm_name=vm_name,
            source_vm_cluster=source_cluster_name,
            state=ovirtsdk4.types.VmStatus.DOWN,
        )


@pytest.mark.polarion("CNV-4387")
def test_two_disks_and_nics_vm_import(
    bridge_network, namespace, secret, source_cluster_name, rhv_provider
):
    vm_config = Source.vms["cirros-2disks2nics"]
    vm_name = vm_config["name"]
    with create_vm_import(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=source_cluster_name,
        target_vm_name=vm_name,
        ovirt_mappings=utils.network_mappings(
            items=[
                utils.POD_MAPPING,
                ResourceMappingItem(
                    target_name="mybridge",
                    target_type="multus",
                    source_name="vm/vm",
                ),
            ]
        ),
        start_vm=True,
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_READY
        )
        check_cnv_vm_config(
            vm=vmimport.vm,
            rhv_provider=rhv_provider,
            source_vm_name=vm_name,
            source_vm_cluster=source_cluster_name,
            expected_vm_config=vm_config,
        )
