import logging

import pytest
from ocp_resources.resource import Resource
from pytest_testconfig import config as py_config

from tests.compute.utils import validate_pause_optional_migrate_unpause_linux_vm
from tests.compute.virt.utils import append_feature_gate_to_hco
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.virt import (
    get_kubevirt_hyperconverged_spec,
    migrate_vm_and_verify,
    running_vm,
    vm_instance_from_template,
)


NONROOT_ANNOTATION = f"{Resource.ApiGroup.KUBEVIRT_IO}/nonroot"
FEATURE_GATE = "NonRootExperimental"
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


def assert_virt_launcher_pod_is_nonroot(vm):
    assert vm.vmi.is_virt_launcher_pod_root, "Virt Launcher Pod is not running as Root."


@pytest.fixture(scope="class")
def enabled_nonroot_featuregate_scope_class(
    hyperconverged_resource_scope_class,
    kubevirt_feature_gates_scope_class,
    admin_client,
    hco_namespace,
):
    kubevirt_feature_gates_scope_class.append(FEATURE_GATE)
    with append_feature_gate_to_hco(
        feature_gate=kubevirt_feature_gates_scope_class,
        resource=hyperconverged_resource_scope_class,
        client=admin_client,
        namespace=hco_namespace,
    ):
        yield


@pytest.fixture()
def enabled_nonroot_featuregate_with_running_vm_and_restored_featuregate(
    hyperconverged_resource_scope_function,
    kubevirt_feature_gates,
    admin_client,
    hco_namespace,
    privilege_based_vm_scope_function,
):
    """Update FeatureGate to Obtain NonRoot VMI and immediately restore FeatureGate after a running_vm.

    1. For a VM with start_vm as False.
    2. Update HCO CR with NonRootExperimental FeatureGate via JSON Annotation Patch.
    3. Start the VM to obtain NonRoot Virt-Launcher Pod based VMI.
    4. Immediately Restore the FeatureGates after we get a running_vm.
    """
    kubevirt_feature_gates.append(FEATURE_GATE)
    with append_feature_gate_to_hco(
        feature_gate=kubevirt_feature_gates,
        resource=hyperconverged_resource_scope_function,
        client=admin_client,
        namespace=hco_namespace,
    ):
        running_vm(vm=privilege_based_vm_scope_function)
        assert_virt_launcher_pod_is_root(vm=privilege_based_vm_scope_function)


@pytest.fixture(scope="class")
def kubevirt_hyperconverged_spec_scope_class(admin_client, hco_namespace):
    return get_kubevirt_hyperconverged_spec(
        admin_client=admin_client, hco_namespace=hco_namespace
    )


@pytest.fixture(scope="class")
def kubevirt_config_scope_class(kubevirt_hyperconverged_spec_scope_class):
    return kubevirt_hyperconverged_spec_scope_class["configuration"]


@pytest.fixture(scope="class")
def kubevirt_feature_gates_scope_class(kubevirt_config_scope_class):
    return kubevirt_config_scope_class["developerConfiguration"]["featureGates"]


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


@pytest.fixture()
def privilege_based_vm_scope_function(
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
    ) as privilege_based_vm_scope_function:
        yield privilege_based_vm_scope_function


@pytest.fixture(scope="class")
def migrated_nonroot_vm_scope_class(
    nonroot_vm_scope_class,
):
    migrate_vm_and_verify(vm=nonroot_vm_scope_class)


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
@pytest.mark.usefixtures(
    "enabled_nonroot_featuregate_scope_class",
)
class TestNonRootVirtLauncherPod:
    @pytest.mark.polarion("CNV-6025")
    def test_nonroot_virtlauncher_vm(
        self,
        nonroot_vm_scope_class,
    ):
        LOGGER.info(
            f"Check {nonroot_vm_scope_class.name} has the annotation {NONROOT_ANNOTATION}"
        )
        assert (
            NONROOT_ANNOTATION
            in nonroot_vm_scope_class.vmi.instance.metadata.annotations.keys()
        ), f"VMI with Non-Root Virt-Launcher Pod should have {NONROOT_ANNOTATION} annotations."
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


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module,",
    [
        pytest.param(
            DATA_VOLUME_DICT,
        ),
    ],
    indirect=True,
)
class TestNonRootVmiPodToggleFeatureGateAndMigrate:
    @pytest.mark.parametrize(
        "privilege_based_vm_scope_function, enabled_featuregate_scope_function,",
        [
            pytest.param(
                {
                    "vm_name": "root-virtlauncher-pod-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                },
                FEATURE_GATE,
                marks=pytest.mark.polarion("CNV-6027"),
                id="test_root_vmipod_remains_root_after_toggle_featuregate_and_migrate",
            ),
        ],
        indirect=True,
    )
    def test_root_virtlauncher_vm(
        self,
        privilege_based_vm_scope_function,
        enabled_featuregate_scope_function,
    ):
        migrate_vm_and_verify(
            vm=privilege_based_vm_scope_function, check_ssh_connectivity=True
        )
        LOGGER.info(f"Check {privilege_based_vm_scope_function.name} VMI remains Root.")
        assert_virt_launcher_pod_is_nonroot(vm=privilege_based_vm_scope_function)

    @pytest.mark.parametrize(
        "privilege_based_vm_scope_function,",
        [
            pytest.param(
                {
                    "vm_name": "nonroot-virtlauncher-pod-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "start_vm": False,
                },
                marks=pytest.mark.polarion("CNV-6028"),
                id="test_nonroot_vmipod_remains_nonroot_after_toggle_featuregate_and_migrate",
            ),
        ],
        indirect=True,
    )
    def test_nonroot_virtlauncher_vm(
        self,
        kubevirt_feature_gates,
        privilege_based_vm_scope_function,
        enabled_nonroot_featuregate_with_running_vm_and_restored_featuregate,
    ):
        migrate_vm_and_verify(
            vm=privilege_based_vm_scope_function, check_ssh_connectivity=True
        )
        LOGGER.info(
            f"Check {privilege_based_vm_scope_function.name} VMI remains NonRoot."
        )
        assert_virt_launcher_pod_is_root(vm=privilege_based_vm_scope_function)
