from resources.virtual_machine import VirtualMachineInstanceMigration


def migrate_vm_and_validate(vm, when):
    vmi_node_before_migration = vm.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name=f"{when}-upgrade-migration", namespace=vm.namespace, vmi=vm.vmi
    ) as mig:
        mig.wait_for_status(status="Succeeded", timeout=720)
        assert vm.vmi.instance.status.nodeName != vmi_node_before_migration
        assert vm.vmi.instance.status.migrationState.completed
