import os
from subprocess import check_output

import pytest
from tests.product_upgrade.utils import migrate_vm_and_validate
from tests.utils import vm_console_run_commands
from utilities import console


@pytest.mark.upgrade
@pytest.mark.incremental
@pytest.mark.usefixtures("skip_when_one_node")
class TestUpgrade:
    @pytest.mark.run(before="test_upgrade")
    @pytest.mark.polarion("CNV-2974")
    def test_is_vm_running_before_upgrade(self, vm_for_upgrade):
        vm_for_upgrade.vmi.wait_until_running()

    @pytest.mark.run(after="test_is_vm_running_before_upgrade")
    @pytest.mark.polarion("CNV-2975")
    def test_migration_before_upgrade(self, vm_for_upgrade):
        migrate_vm_and_validate(vm=vm_for_upgrade, when="before")

    @pytest.mark.run(after="test_migration_before_upgrade")
    @pytest.mark.polarion("CNV-2988")
    def test_vm_have_2_interfaces_before_upgrade(self, vm_for_upgrade):
        assert len(vm_for_upgrade.vmi.interfaces) == 2

    @pytest.mark.run(after="test_migration_before_upgrade")
    @pytest.mark.polarion("CNV-2987")
    def test_vm_console_before_upgrade(self, vm_for_upgrade):
        vm_console_run_commands(
            console_impl=console.RHEL,
            vm=vm_for_upgrade,
            commands=["ls"],
            console_timeout=1100,
        )

    @pytest.mark.polarion("CNV-2991")
    def test_upgrade(self, vm_for_upgrade):
        target_hco_version = os.environ.get("UPGRADE_TO_VERSION", "")
        check_output(
            "curl -k https://pkgs.devel.redhat.com/cgit/containers/hco-bundle-registry/plain/qe-upgrade.sh?h="
            f"cnv-2.1-rhel-8 | bash -x -s HCO_BUNDLE_REGISTRY_TAG={target_hco_version}",
            shell=True,
        )

    @pytest.mark.run(after="test_upgrade")
    @pytest.mark.polarion("CNV-2978")
    def test_is_vm_running_after_upgrade(self, vm_for_upgrade):
        vm_for_upgrade.vmi.wait_until_running()

    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    @pytest.mark.polarion("CNV-2989")
    def test_vm_have_2_interfaces_after_upgrade(self, vm_for_upgrade):
        assert len(vm_for_upgrade.vmi.interfaces) == 2

    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    @pytest.mark.polarion("CNV-2980")
    def test_vm_console_after_upgrade(self, vm_for_upgrade):
        vm_console_run_commands(
            console_impl=console.RHEL,
            vm=vm_for_upgrade,
            commands=["ls"],
            console_timeout=1100,
        )

    @pytest.mark.run(after="test_vm_console_after_upgrade")
    @pytest.mark.polarion("CNV-2979")
    def test_migration_after_upgrade(self, vm_for_upgrade):
        migrate_vm_and_validate(vm=vm_for_upgrade, when="after")
        assert len(vm_for_upgrade.vmi.interfaces) == 2
        vm_console_run_commands(
            console_impl=console.RHEL, vm=vm_for_upgrade, commands=["ls"], timeout=1100
        )
