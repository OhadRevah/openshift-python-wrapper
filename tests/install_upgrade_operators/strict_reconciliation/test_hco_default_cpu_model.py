import pytest
from ocp_resources.kubevirt import KubeVirt

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


HCO_CPU_MODEL_KEY = "defaultCPUModel"
KUBEVIRT_CPU_MODEL_KEY = "cpuModel"
VMI_CPU_MODEL_KEY = "host-model"

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


def assert_hco_updated_default_cpu_model(hco_resource, expected_cpu_model):
    hco_cpu_model = hco_resource.instance.spec.get(HCO_CPU_MODEL_KEY)
    assert hco_cpu_model == expected_cpu_model, (
        f"hco should have CPU model: '{expected_cpu_model}' but found "
        f"with incorrect CPU model: '{hco_cpu_model}"
    )


def assert_vmi_cpu_model(vmi_resource, expected_cpu_model):
    vmi_cpu_model = vmi_resource.vmi.instance.spec.domain.cpu.get("model")
    assert vmi_cpu_model == expected_cpu_model, (
        f"vmi should have CPU model '{expected_cpu_model}' but found "
        f"with incorrect CPU model: '{vmi_cpu_model}'"
    )


def assert_kubevirt_cpu_model(kubevirt_resource, expected_cpu_model):
    kubevirt_cpu_model = kubevirt_resource.instance.spec["configuration"].get(
        KUBEVIRT_CPU_MODEL_KEY
    )
    assert kubevirt_cpu_model == expected_cpu_model, (
        f"kubevirt should have CPU model: '{expected_cpu_model}' but found "
        f"with incorrect CPU model: '{kubevirt_cpu_model}'"
    )


@pytest.fixture()
def fedora_vm_for_test(unprivileged_client, namespace):
    name = "fedora-vm-for-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        running=True,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def hco_with_default_cpu_model_updated(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    nodes_common_cpu_model,
):
    patch = {
        "spec": {
            HCO_CPU_MODEL_KEY: nodes_common_cpu_model,
        }
    }
    with ResourceEditorValidateHCOReconcile(
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        patches={hyperconverged_resource_scope_function: patch},
    ):
        yield nodes_common_cpu_model


@pytest.mark.polarion("CNV-9024")
def test_default_value_for_cpu_model(
    hco_spec_scope_module,
    kubevirt_hyperconverged_spec_scope_module,
    fedora_vm_for_test,
):
    """
    Default value for defaultCPUModel should be 'None' in HCO
    Default value for cpu model in kubevirt should be 'None'
    and for VMI should be 'host-model'
    """
    assert (
        HCO_CPU_MODEL_KEY not in hco_spec_scope_module
    ), f"HCO contains value for '{HCO_CPU_MODEL_KEY}',HCO spec values are:{hco_spec_scope_module}"
    assert (
        KUBEVIRT_CPU_MODEL_KEY
        not in kubevirt_hyperconverged_spec_scope_module["configuration"]
    ), (
        f"Kubevirt contains value for '{KUBEVIRT_CPU_MODEL_KEY}', "
        f"kubevirt spec values are:{kubevirt_hyperconverged_spec_scope_module}"
    )
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_for_test,
        expected_cpu_model=VMI_CPU_MODEL_KEY,
    )


@pytest.mark.polarion("CNV-9025")
def test_set_hco_default_cpu_model(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    kubevirt_resource,
    hco_with_default_cpu_model_updated,
    fedora_vm_for_test,
):
    """
    Test that CPU model in kubevirt and vmi are the same as set in HCO
    """
    assert_hco_updated_default_cpu_model(
        hco_resource=hyperconverged_resource_scope_function,
        expected_cpu_model=hco_with_default_cpu_model_updated,
    )
    assert_kubevirt_cpu_model(
        kubevirt_resource=kubevirt_resource,
        expected_cpu_model=hco_with_default_cpu_model_updated,
    )
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_for_test,
        expected_cpu_model=hco_with_default_cpu_model_updated,
    )


@pytest.mark.polarion("CNV-9026")
def test_set_hco_default_cpu_model_with_existing_vm(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    kubevirt_resource,
    fedora_vm_for_test,
    hco_with_default_cpu_model_updated,
):
    """
    When defaultCPUModel is set in HCO, it should reflect in kubevirt
    and also with VMI. If VM is already running even before updating
    defaultCPUModel in HCO,then restarting the VM should reflect the
    new CPU model in VMI
    """
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_for_test,
        expected_cpu_model=VMI_CPU_MODEL_KEY,
    )
    fedora_vm_for_test.restart(wait=True)
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_for_test,
        expected_cpu_model=hco_with_default_cpu_model_updated,
    )
