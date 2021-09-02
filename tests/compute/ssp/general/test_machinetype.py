# -*- coding: utf-8 -*-

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError

from tests.compute.ssp import utils as ssp_utils
from tests.compute.utils import update_hco_config, wait_for_updated_kv_value
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
    wait_for_vm_interfaces,
)


pytestmark = pytest.mark.post_upgrade


@pytest.fixture()
def vm(request, cluster_cpu_model_scope_function, unprivileged_client, namespace):
    name = f"vm-{request.param['vm_name']}-machine-type"

    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        machine_type=request.param.get("machine_type"),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def updated_configmap_machine_type(
    request,
    hyperconverged_resource_scope_function,
    kubevirt_config,
    admin_client,
    hco_namespace,
):
    machine_type = request.param["machine_type"]
    with update_hco_config(
        resource=hyperconverged_resource_scope_function,
        path="machineType",
        value=machine_type,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=["machineType"],
            value=machine_type,
        )
        yield


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
def test_default_machine_type(machine_type_from_kubevirt_config, vm):
    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config
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
    machine_type_from_kubevirt_config,
    vm,
):
    migrate_vm_and_verify(vm=vm)

    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config
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
    machine_type_from_kubevirt_config,
    vm,
    updated_configmap_machine_type,
):
    """Test machine type change in ConfigMap; existing VM does not get new
    value after restart or migration"""

    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config
    )

    vm.restart(wait=True)
    wait_for_vm_interfaces(vmi=vm.vmi)
    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config
    )

    migrate_vm_and_verify(vm=vm)

    ssp_utils.validate_machine_type(
        vm=vm, expected_machine_type=machine_type_from_kubevirt_config
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
    """Test machine type change in ConfigMap; new VM gets new value"""

    ssp_utils.validate_machine_type(vm=vm, expected_machine_type="pc-q35-rhel8.1.0")


@pytest.mark.polarion("CNV-3688")
def test_unsupported_machine_type(namespace, unprivileged_client):
    vm_name = "vm-invalid-machine-type"

    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace.name,
            body=fedora_vm_body(name=vm_name),
            client=unprivileged_client,
            machine_type="pc-i440fx",
        ):
            pytest.fail("VM created with invalid machine type.")


@pytest.mark.polarion("CNV-5658")
def test_major_release_machine_type(machine_type_from_kubevirt_config):
    # CNV should always use a major release for machine type, for example: pc-q35-rhel8.3.0
    assert machine_type_from_kubevirt_config.endswith(
        ".0"
    ), f"Machine type should be a major release {machine_type_from_kubevirt_config}"
