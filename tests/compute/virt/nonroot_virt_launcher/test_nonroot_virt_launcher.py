import logging

import pytest
from ocp_resources.resource import Resource
from pytest_testconfig import config as py_config

from tests.compute.utils import validate_pause_optional_migrate_unpause_linux_vm
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.virt import (
    migrate_vm_and_verify,
    vm_instance_from_template,
    wait_for_kubevirt_conditions,
)


NONROOT_ANNOTATION = f"{Resource.ApiGroup.KUBEVIRT_IO}/nonroot"
DATA_VOLUME_DICT = {
    "dv_name": RHEL_LATEST_OS,
    "image": RHEL_LATEST["image_path"],
    "storage_class": py_config["default_storage_class"],
    "dv_size": RHEL_LATEST["dv_size"],
}
LOGGER = logging.getLogger(__name__)


def assert_virt_launcher_pod_is_root(vm):
    assert (
        not vm.vmi.is_virt_launcher_pod_root
    ), "Virt Launcher Pod should not be running as Root."


@pytest.fixture(scope="class")
def nonroot_vm_scope_class(
    request,
    unprivileged_client,
    namespace,
    golden_image_dv_scope_module_data_source_scope_class,
    nodes_common_cpu_model,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_dv_scope_module_data_source_scope_class,
        vm_cpu_model=nodes_common_cpu_model,
    ) as nonroot_vm_scope_class:
        yield nonroot_vm_scope_class


@pytest.fixture(scope="class")
def migrated_nonroot_vm_scope_class(
    nonroot_vm_scope_class,
):
    migrate_vm_and_verify(vm=nonroot_vm_scope_class)


@pytest.fixture()
def hco_cr_with_nonroot_featuregate_as_false(
    hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {
                    "featureGates": {
                        "nonRoot": False,
                    }
                }
            }
        },
    ):
        wait_for_kubevirt_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        yield


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, nonroot_vm_scope_class,",
    [
        pytest.param(
            DATA_VOLUME_DICT,
            {
                "vm_name": "nonroot-virtlauncher-vm",
                "template_labels": RHEL_LATEST_LABELS,
            },
        ),
    ],
    indirect=True,
)
class TestNonRootVirtLauncherPod:
    @pytest.mark.polarion("CNV-6025")
    def test_nonroot_virtlauncher_vm(
        self,
        nonroot_vm_scope_class,
    ):
        assert (
            nonroot_vm_scope_class.vmi.instance.status.runtimeUser != 0
        ), "VMI with non-root virt-launcher pod should have a user_id other than root user_id 0."
        assert_virt_launcher_pod_is_root(vm=nonroot_vm_scope_class)

    @pytest.mark.polarion("CNV-6812")
    def test_nonroot_virtlauncher_pause_unpause_after_migration(
        self,
        nonroot_vm_scope_class,
        migrated_nonroot_vm_scope_class,
    ):
        assert_virt_launcher_pod_is_root(vm=nonroot_vm_scope_class)
        validate_pause_optional_migrate_unpause_linux_vm(vm=nonroot_vm_scope_class)

    @pytest.mark.polarion("CNV-6813")
    def test_nonroot_virtlauncher_pause_migrate_unpause(
        self,
        nonroot_vm_scope_class,
    ):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=nonroot_vm_scope_class, migrate=True
        )
        assert_virt_launcher_pod_is_root(vm=nonroot_vm_scope_class)


@pytest.mark.polarion("CNV-8520")
def test_default_nonroot_featuregate_in_hco_cr(hco_spec, kubevirt_feature_gates):
    assert hco_spec["featureGates"][
        "nonRoot"
    ], f"NonRoot Feature Gate is set as {hco_spec['featureGates']['nonRoot']} in HCO CR"
    assert (
        "NonRoot" in kubevirt_feature_gates
    ), f"FeatureGates does not have NonRoot in the List {kubevirt_feature_gates}"


@pytest.mark.polarion("CNV-8521")
def test_nonroot_featuregate_false(
    hco_cr_with_nonroot_featuregate_as_false, hco_spec, kubevirt_feature_gates
):
    assert not hco_spec["featureGates"][
        "nonRoot"
    ], f"NonRoot Feature Gate is set as {hco_spec['featureGates']['nonRoot']} in HCO CR"
    assert (
        "NonRoot" not in kubevirt_feature_gates
    ), f"FeatureGates have NonRoot in the List {kubevirt_feature_gates}"
