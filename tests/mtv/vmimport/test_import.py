import logging
import multiprocessing

import ovirtsdk4.types
import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.secret import Secret
from ocp_resources.utils import TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_import import VirtualMachineImport

from tests.mtv.vmimport import utils
from tests.mtv.vmimport.utils import ResourceMappingItem, Source
from utilities.constants import TIMEOUT_10MIN
from utilities.storage import get_storage_class_dict_from_matrix
from utilities.virt import import_vm, wait_for_guest_agent


LOGGER = logging.getLogger(__name__)


def _test_import_vm(
    name,
    namespace,
    provider_credentials_secret_name,
    provider_credentials_secret_namespace,
    vm_name,
    cluster_name,
    target_vm_name,
    provider_data,
    provider_type,
    vm_config,
    start_vm=True,
    provider=None,
    provider_mappings=None,
    resource_mapping_name=None,
    resource_mapping_namespace=None,
    wait_for_guest_os=False,
):
    with import_vm(
        name=name,
        namespace=namespace,
        provider_credentials_secret_name=provider_credentials_secret_name,
        provider_credentials_secret_namespace=provider_credentials_secret_namespace,
        vm_name=vm_name,
        cluster_name=cluster_name,
        target_vm_name=target_vm_name,
        start_vm=start_vm,
        provider_type=provider_type,
        provider_mappings=provider_mappings,
        resource_mapping_namespace=resource_mapping_namespace,
        resource_mapping_name=resource_mapping_name,
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_RUNNING
            if start_vm
            else VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_READY
        )
        vmimport.vm.vmi.wait_until_running()

        check_cnv_vm_config(
            vm=vmimport.vm,
            provider=provider,
            provider_data=provider_data,
            source_vm_name=vm_name,
            expected_vm_config=vm_config,
        )

        if wait_for_guest_os:
            wait_for_guest_agent(vmi=vmimport.vm.vmi)


def import_name(vm_name):
    return f"{vm_name}-import"


def wait_for_source_vm_status(provider, provider_data, source_vm_name, state):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=provider.vm,
        name=source_vm_name,
        cluster=provider_data["cluster_name"],
    )
    for sample in samples:
        if sample.status == state:
            break


def check_cnv_vm_network_config(
    vm, source_vm_name, expected_vm_config, provider_data, provider=None
):
    cnv_vm_network_interfaces = vm.get_interfaces()
    number_of_cnv_vm_network_interfaces = (
        len(cnv_vm_network_interfaces) if cnv_vm_network_interfaces is not None else 0
    )

    assert (
        number_of_cnv_vm_network_interfaces == expected_vm_config["network_interfaces"]
    ), "Wrong number of network interfaces"

    if provider and hasattr(provider, "vm_nics"):
        failed_assert_msgs = []
        for nic_index, source_vm_nic in enumerate(
            provider.vm_nics(
                vm=provider.vm(
                    name=source_vm_name, cluster=provider_data["cluster_name"]
                )
            )
        ):
            cnv_vm_mac = cnv_vm_network_interfaces[nic_index].macAddress
            source_vm_mac = source_vm_nic.mac.address
            if cnv_vm_mac != source_vm_mac:
                failed_assert_msgs.append(
                    f"mac address for nic {source_vm_nic.name} check failed, "
                    f"Expected:{source_vm_mac}, Actual: {cnv_vm_mac}"
                )

        assert not failed_assert_msgs, f"Failed verifications: {failed_assert_msgs}"


def check_cnv_vm_cpu_config(vm, expected_vm_config):
    machine = vm.instance.spec.template.spec.domain.machine
    cpu = vm.instance.spec.template.spec.domain.cpu
    check_values = {
        "cpu_cores": cpu.cores,
        "cpu_sockets": cpu.sockets,
        "cpu_threads": cpu.threads,
        "machine_type": machine.type,
    }
    # cpu threading is optional.source vm may not support it.
    if not getattr(cpu, "threads"):
        check_values.pop("cpu_threads")

    failed_assert_msgs = []
    for check, value in check_values.items():
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

    # to keep it simple,
    # we expect all cnv disks to be of the same
    # storage class
    if expected_vm_config.get("expected_storage_class"):
        failed_assert_msgs = []
        expected_storage_class = expected_vm_config["expected_storage_class"]
        for dv in vm.instance.spec.template.spec.volumes:
            pvc = PersistentVolumeClaim(namespace=vm.namespace, name=dv.dataVolume.name)
            storage_class_name = pvc.instance.spec.storageClassName
            if storage_class_name != expected_storage_class:
                failed_assert_msgs.append(
                    f"data volume {dv.dataVolume.name} storage class check failed, "
                    f"Expected: {expected_storage_class},"
                    f"Actual: {storage_class_name}"
                )
        assert not failed_assert_msgs, f"Failed verifications: {failed_assert_msgs}"


def check_cnv_vm_config(
    vm,
    provider,
    source_vm_name,
    provider_data,
    expected_vm_config,
):
    assert vm.exists, f"vm {source_vm_name} does not exist."

    assert (
        vm.instance.metadata.name == expected_vm_config["name"]
    ), "vm name check failed"

    check_cnv_vm_cpu_config(vm=vm, expected_vm_config=expected_vm_config)

    check_cnv_vm_network_config(
        vm=vm,
        provider=provider,
        provider_data=provider_data,
        source_vm_name=source_vm_name,
        expected_vm_config=expected_vm_config,
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
def test_vm_import(
    namespace,
    provider_data,
    provider,
    secret,
    vm_key,
    providers_mapping_network_only,
    no_vms_in_namespace,
    default_sc_multi_storage,
):
    vm_config = Source.vms[vm_key]
    vm_name = vm_config["name"]

    _test_import_vm(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=provider_data["cluster_name"],
        target_vm_name=vm_name,
        provider_data=provider_data,
        provider_type=provider_data["type"],
        vm_config=vm_config,
        start_vm=True,
        provider=provider,
        provider_mappings=providers_mapping_network_only,
        wait_for_guest_os=vm_config.get("guest_agent", False),
    )


@pytest.mark.polarion("CNV-4392")
def test_cancel_vm_import(
    skip_if_vmware_provider,
    admin_client,
    namespace,
    provider_data,
    provider,
    secret,
    no_vms_in_namespace,
    default_sc_multi_storage,
):
    vm_name = Source.vms["cirros-no-nics"]["name"]
    cluster_name = provider_data["cluster_name"]

    with import_vm(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=cluster_name,
        target_vm_name=vm_name,
        provider_type=provider_data["type"],
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.ProcessingConditionReason.COPYING_DISKS,
            cond_type=VirtualMachineImport.Condition.PROCESSING,
        )
    # We need to use assert wait because it takes some time until the resources
    # are deleted.

    VirtualMachine(name=vm_name, namespace=namespace.name).wait_deleted()

    if provider:
        source_vm = provider.vm(name=vm_name, cluster=cluster_name)
        vm_disk_id = provider.vm_disk_attachments(vm=source_vm)[0].id
        DataVolume(
            name=f"{import_name(vm_name=vm_name)}-{vm_disk_id}",
            namespace=namespace.name,
            privileged_client=admin_client,
        ).wait_deleted()

    for resource in (Secret, ConfigMap):
        for resource_object in resource.get(
            dyn_client=admin_client,
            label_selector=utils.make_labels(import_name(vm_name=vm_name)),
        ):
            resource_object.wait_deleted()


@pytest.mark.polarion("CNV-4391")
def test_running_vm_import(
    skip_if_vmware_provider,
    namespace,
    provider_data,
    provider,
    providers_mapping_network_only,
    secret,
    no_vms_in_namespace,
    default_sc_multi_storage,
):
    vm_config = Source.vms["cirros-running"]
    vm_name = vm_config["name"]

    _test_import_vm(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=provider_data["cluster_name"],
        target_vm_name=vm_name,
        provider_data=provider_data,
        provider_type=provider_data["type"],
        vm_config=vm_config,
        start_vm=True,
        provider=provider,
        provider_mappings=providers_mapping_network_only,
    )

    wait_for_source_vm_status(
        provider=provider,
        provider_data=provider_data,
        source_vm_name=vm_name,
        state=ovirtsdk4.types.VmStatus.DOWN,
    )


@pytest.mark.parametrize(
    "providers_mapping_network_only",
    [
        pytest.param(Source.vms["cirros-2disks2nics"]["network_interfaces"]),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-4387")
def test_two_disks_and_nics_vm_import(
    namespace,
    vm_import_bridge_device,
    provider_data,
    provider,
    secret,
    providers_mapping_network_only,
    no_vms_in_namespace,
    default_sc_multi_storage,
):
    vm_config = Source.vms["cirros-2disks2nics"]
    vm_name = vm_config["name"]
    cluster_name = provider_data["cluster_name"]

    with import_vm(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=cluster_name,
        target_vm_name=vm_name,
        provider_mappings=providers_mapping_network_only,
        provider_type=provider_data["type"],
        start_vm=True,
    ) as vmimport:
        vmimport.wait(
            cond_reason=VirtualMachineImport.SucceededConditionReason.VIRTUAL_MACHINE_RUNNING
        )
        vmimport.vm.vmi.wait_until_running()
        check_cnv_vm_config(
            vm=vmimport.vm,
            provider=provider,
            provider_data=provider_data,
            source_vm_name=vm_name,
            expected_vm_config=vm_config,
        )


@pytest.mark.parametrize(
    "vm_key",
    [
        pytest.param("usbenabled", marks=(pytest.mark.polarion("CNV-4398"))),
        pytest.param("nodisk", marks=(pytest.mark.polarion("CNV-4468"))),
        pytest.param("notemplate", marks=(pytest.mark.polarion("CNV-4473"))),
    ],
)
def test_invalid_vm_import(
    skip_if_vmware_provider,
    provider,
    namespace,
    provider_data,
    providers_mapping_network_only,
    secret,
    vm_key,
    no_vms_in_namespace,
):
    vm_config = Source.vms[vm_key]
    vm_name = vm_config["name"]
    cluster_name = provider_data["cluster_name"]

    with import_vm(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=cluster_name,
        target_vm_name=vm_name,
        start_vm=True,
        provider_mappings=providers_mapping_network_only,
        provider_type=provider_data["type"],
    ) as vmimport:
        expected_import_status = vm_config["expected_import_status"]
        vmimport.wait(
            cond_reason=expected_import_status["reason"],
            cond_status=expected_import_status["status"],
            cond_type=expected_import_status["type"],
        )


@pytest.mark.parametrize(
    "resource_mapping, skip_if_less_than_x_storage_classes",
    [
        pytest.param(
            "cirros-3disks",
            3,
            marks=(pytest.mark.polarion("CNV-4393")),
        ),
    ],
    indirect=True,
)
def test_vmimport_with_mixed_external_and_internal_storage_mappings(
    skip_if_less_than_x_storage_classes,
    provider,
    provider_data,
    namespace,
    secret,
    resource_mapping,
    no_vms_in_namespace,
    storage_class_matrix__function__,
):

    # Verify:
    # 1. External Storage Mapping (Disk0 expected StorageClass: global_config default sc)
    # 2. Override 1 Storage Name with Internal Mapping  (Disk1 expected StorageClass: global_config default sc)
    # 3. Override 1 Disk name with InternalMapping  (Disk2 expected StorageClass: global_config default sc)

    expected_vm_config = Source.vms[f"cirros-3disks-{provider_data['fqdn']}"]
    expected_vm_name = expected_vm_config["name"]
    source_data_volumes_config = expected_vm_config["volumes_details"]
    expected_storage_class = [*storage_class_matrix__function__][0]

    # in the internal mapping we use  the same destination storage class&volume mode for all items
    _storage_dict = get_storage_class_dict_from_matrix(
        storage_class=expected_storage_class
    )[expected_storage_class]
    _vol_mod = _storage_dict["volume_mode"]
    _acc_mod = _storage_dict["access_mode"]

    # all 3 disks are expected to be of the global_config default storage class at the end.
    expected_vm_config["expected_storage_class"] = expected_storage_class

    _test_import_vm(
        name=import_name(vm_name=expected_vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=expected_vm_name,
        cluster_name=provider_data["cluster_name"],
        target_vm_name=expected_vm_name,
        start_vm=True,
        provider_type=provider_data["type"],
        provider_mappings=utils.ProviderMappings(
            storage_mappings=[
                ResourceMappingItem(
                    target_name=expected_storage_class,  # disk1 is overridden by Storage Name
                    source_name=source_data_volumes_config[1]["storage_name"],
                    target_volume_mode=_vol_mod,
                    target_access_modes=_acc_mod,
                ),
            ],
            disk_mappings=[
                ResourceMappingItem(
                    target_name=expected_storage_class,  # disk2 is overridden by DiskName
                    source_name=source_data_volumes_config[2]["disk_name"],
                    target_volume_mode=_vol_mod,
                    target_access_modes=_acc_mod,
                )
            ],
        ),
        resource_mapping_name=resource_mapping.name,
        resource_mapping_namespace=resource_mapping.namespace,
        provider_data=provider_data,
        vm_config=expected_vm_config,
    )


@pytest.mark.parametrize(
    "vm_key",
    [
        pytest.param(
            "no-vnic-profile",
            marks=(pytest.mark.polarion("CNV-4467")),
        ),
        pytest.param(
            "cirros-no-nics",
            marks=(pytest.mark.polarion("CNV-4469")),
        ),
    ],
)
def test_vm_import_no_mappings(
    skip_if_vmware_provider,
    namespace,
    provider_data,
    provider,
    secret,
    vm_key,
    no_vms_in_namespace,
    default_sc_multi_storage,
):
    vm_config = Source.vms[vm_key]
    vm_name = vm_config["name"]
    cluster_name = provider_data["cluster_name"]

    _test_import_vm(
        name=import_name(vm_name=vm_name),
        namespace=namespace.name,
        provider_credentials_secret_name=secret.name,
        provider_credentials_secret_namespace=secret.namespace,
        vm_name=vm_name,
        cluster_name=cluster_name,
        target_vm_name=vm_name,
        start_vm=True,
        provider_type=provider_data["type"],
        provider_data=provider_data,
        vm_config=vm_config,
    )


@pytest.mark.polarion("CNV-4397")
def test_two_vms_parallel_import(
    namespace,
    provider_data,
    provider,
    secret,
    providers_mapping_network_only,
    default_sc_multi_storage,
):
    vmimport_jobs = []
    for vm in ["cirros", "cirros2"]:
        vm_name = Source.vms[vm]["name"]
        vm_import_kwargs = {
            "name": import_name(vm_name=vm_name),
            "namespace": namespace.name,
            "provider_credentials_secret_name": secret.name,
            "provider_credentials_secret_namespace": secret.namespace,
            "vm_name": vm_name,
            "cluster_name": provider_data["cluster_name"],
            "target_vm_name": vm_name,
            "provider_data": provider_data,
            "provider_type": provider_data["type"],
            "vm_config": Source.vms[vm],
            "start_vm": True,
            "provider": provider,
            "provider_mappings": providers_mapping_network_only,
        }
        vmimport_proc = multiprocessing.Process(
            target=_test_import_vm, kwargs=vm_import_kwargs
        )
        vmimport_jobs.append(vmimport_proc)
        vmimport_proc.start()

    for process in vmimport_jobs:
        process.join()
    assert set([process.exitcode for process in vmimport_jobs]) == {0}
