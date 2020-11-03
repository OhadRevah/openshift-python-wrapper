# -*- coding: utf-8 -*-

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
from resources.resource import ResourceEditor
from tests.compute.ssp import utils as ssp_utils
from tests.compute.utils import migrate_vm
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture()
def vm(request, unprivileged_client, namespace):
    name = f"vm-{request.param['vm_name']}-machine-type"

    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
        machine_type=request.param.get("machine_type"),
    ) as vm:
        vm.start()
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def updated_configmap_machine_type(request, kubevirt_config_cm):
    with ResourceEditor(
        patches={
            kubevirt_config_cm: {
                "data": {"machine-type": request.param["machine_type"]}
            }
        }
    ) as edits:
        yield edits


@pytest.mark.parametrize(
    "vm",
    [
        pytest.param(
            {"vm_name": "default"},
            marks=pytest.mark.polarion("CNV-3312"),
        )
    ],
    indirect=True,
)
def test_default_machine_type(machine_type_from_kubevirt_config_cm, vm):
    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config_cm
    )


@pytest.mark.parametrize(
    "vm, expected",
    [
        pytest.param(
            {"vm_name": "pc-q35", "machine_type": "pc-q35-rhel7.6.0"},
            "pc-q35-rhel7.6.0",
            marks=pytest.mark.polarion("CNV-3311"),
        )
    ],
    indirect=["vm"],
)
def test_pc_q35_vm_machine_type(vm, expected):
    ssp_utils.validate_machine_type(vm=vm, expected_machine_type=expected)


@pytest.mark.parametrize(
    "vm",
    [
        pytest.param(
            {"vm_name": "machine-type-mig"},
            marks=pytest.mark.polarion("CNV-3323"),
        )
    ],
    indirect=True,
)
def test_migrate_vm(
    skip_rhel7_workers,
    machine_type_from_kubevirt_config_cm,
    vm,
):
    migrate_vm(vm=vm)

    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config_cm
    )


@pytest.mark.parametrize(
    "vm, updated_configmap_machine_type",
    [
        pytest.param(
            {"vm_name": "default-cm"},
            {"machine_type": "pc-q35-rhel8.1.0"},
            marks=pytest.mark.polarion("CNV-4347"),
        )
    ],
    indirect=True,
)
def test_machine_type_after_cm_update(
    machine_type_from_kubevirt_config_cm,
    vm,
    updated_configmap_machine_type,
):
    """Test machine type change in ConfigMap; existing VM does not get new
    value after restart or migration"""

    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config_cm
    )

    vm.restart()
    wait_for_vm_interfaces(vmi=vm.vmi)
    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config_cm
    )

    migrate_vm(vm=vm)

    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config_cm
    )


@pytest.mark.parametrize(
    "vm, updated_configmap_machine_type",
    [
        pytest.param(
            {"vm_name": "updated-cm"},
            {"machine_type": "pc-q35-rhel8.1.0"},
            marks=pytest.mark.polarion("CNV-3681"),
        )
    ],
    indirect=True,
)
def test_machine_type_cm_update(updated_configmap_machine_type, vm):
    """ Test machine type change in ConfigMap; new VM gets new value """

    ssp_utils.validate_machine_type(vm=vm, expected_machine_type="pc-q35-rhel8.1.0")


@pytest.mark.polarion("CNV-3688")
def test_unsupported_machine_type(namespace, unprivileged_client):
    vm_name = "vm-invalid-machine-type"

    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace.name,
            body=fedora_vm_body(name=vm_name),
            cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
            client=unprivileged_client,
            machine_type="pc-i440fx",
        ):
            pytest.fail("VM created with invalid machine type.")
