import logging
import os

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.compute.upgrade.constants import SRC_PVC_NAME
from tests.compute.upgrade.utils import (
    mismatching_src_pvc_names,
    verify_vms_ssh_connectivity,
)
from utilities import console
from utilities.constants import (
    DEPENDENCY_SCOPE_SESSION,
    UPGRADE_TEST_DEPENDNCY_NODE_ID,
    UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.exceptions import ResourceValueError
from utilities.virt import migrate_vm_and_verify, vm_console_run_commands


LOGGER = logging.getLogger(__name__)
DEPENDENCIES_NODE_ID_PREFIX = f"{os.path.abspath(__file__)}::" "TestUpgradeCompute"
VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID = (
    f"{DEPENDENCIES_NODE_ID_PREFIX}::test_is_vm_running_before_upgrade"
)
VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID = (
    f"{DEPENDENCIES_NODE_ID_PREFIX}::test_is_vm_running_after_upgrade"
)

pytestmark = pytest.mark.usefixtures("skip_when_one_node", "cnv_upgrade_path")


@pytest.mark.upgrade
@pytest.mark.usefixtures(
    "base_templates",
)
class TestUpgradeCompute:
    """Pre-upgrade tests"""

    @pytest.mark.polarion("CNV-2974")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID)
    def test_is_vm_running_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.vmi.status == VirtualMachineInstance.Status.RUNNING

    @pytest.mark.polarion("CNV-2975")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_migration_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_migration_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if DataVolume.AccessMode.RWO in vm.access_modes:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            migrate_vm_and_verify(
                vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False
            )

    @pytest.mark.polarion("CNV-2988")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_have_2_interfaces_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_have_2_interfaces_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2987")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_console_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_console_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=["ls"])

    @pytest.mark.polarion("CNV-4208")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_ssh_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_ssh_before_upgrade(self, vms_for_upgrade):
        verify_vms_ssh_connectivity(vms_list=vms_for_upgrade)

    @pytest.mark.polarion("CNV-6999")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_run_strategy_before_upgrade"
    )
    def test_vm_run_strategy_before_upgrade(
        self,
        manual_run_strategy_vm,
        always_run_strategy_vm,
        running_manual_run_strategy_vm,
        running_always_run_strategy_vm,
    ):
        verify_vms_ssh_connectivity(
            vms_list=[manual_run_strategy_vm, always_run_strategy_vm]
        )

    @pytest.mark.polarion("CNV-7243")
    @pytest.mark.order(before=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_windows_vm_before_upgrade"
    )
    def test_windows_vm_before_upgrade(
        self,
        windows_vm,
    ):
        verify_vms_ssh_connectivity(vms_list=[windows_vm])

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-2978")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID,
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_is_vm_running_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm.vmi.wait_until_running()

    @pytest.mark.polarion("CNV-2989")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_have_2_interfaces_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_have_2_interfaces_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2980")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_console_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_console_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=["ls"])

    @pytest.mark.polarion("CNV-4209")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_ssh_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_ssh_after_upgrade(self, vms_for_upgrade):
        verify_vms_ssh_connectivity(vms_list=vms_for_upgrade)

    @pytest.mark.polarion("CNV-7000")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_run_strategy_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_run_strategy_after_upgrade(
        self, manual_run_strategy_vm, always_run_strategy_vm
    ):
        verify_vms_ssh_connectivity(
            vms_list=[manual_run_strategy_vm, always_run_strategy_vm]
        )

    @pytest.mark.polarion("CNV-7244")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_windows_vm_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_windows_vm_after_upgrade(
        self,
        windows_vm,
    ):
        verify_vms_ssh_connectivity(vms_list=[windows_vm])

    @pytest.mark.polarion("CNV-2979")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            UPGRADE_TEST_DEPENDNCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_migration_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_migration_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if DataVolume.AccessMode.RWO in vm.access_modes:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            migrate_vm_and_verify(vm=vm)
            assert len(vm.vmi.interfaces) == 2
            vm_console_run_commands(
                console_impl=console.RHEL, vm=vm, commands=["ls"], timeout=1100
            )

    @pytest.mark.polarion("CNV-3682")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_machine_type_after_upgrade(
        self, vms_for_upgrade, vms_for_upgrade_dict_before
    ):
        for vm in vms_for_upgrade:
            assert (
                vm.instance.spec.template.spec.domain.machine.type
                == vms_for_upgrade_dict_before[vm.name]["spec"]["template"]["spec"][
                    "domain"
                ]["machine"]["type"]
            )

    @pytest.mark.polarion("CNV-5932")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vmi_pod_image_updates_after_upgrade_optin(
        self,
        unupdated_vmi_pods_names,
    ):
        """
        Check that the VMI Pods use the latest images after the upgrade
        """
        assert (
            not unupdated_vmi_pods_names
        ), f"The following VMI Pods were not updated: {unupdated_vmi_pods_names}"

    @pytest.mark.polarion("CNV-5749")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_golden_image_pvc_names_after_upgrade(
        self, base_templates, base_templates_after_upgrade
    ):
        LOGGER.info(
            f"Comparing default value for parameter {SRC_PVC_NAME} "
            f"in base templates before and after upgrade"
        )
        mismatching_templates = mismatching_src_pvc_names(
            pre_upgrade_templates=base_templates,
            post_upgrade_templates=base_templates_after_upgrade,
        )

        if mismatching_templates:
            raise ResourceValueError(
                f"Golden image default {SRC_PVC_NAME} "
                f"mismatch after upgrade:\n{mismatching_templates}"
            )