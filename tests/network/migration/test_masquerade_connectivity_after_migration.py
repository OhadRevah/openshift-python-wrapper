# -*- coding: utf-8 -*-

"""
Network Migration - masquerade connectivity after migration
"""

import logging

import pytest
from ocp_resources.utils import TimeoutSampler

from utilities import console
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
    vm_console_run_commands,
    wait_for_console,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def vm_static(
    unprivileged_client,
    namespace,
):
    name = "vm-static"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vm_for_migration(
    unprivileged_client,
    nodes_common_cpu_model,
    namespace,
):
    name = "vm-for-migration"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cpu_model=nodes_common_cpu_model,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vm_static(vm_static):
    return running_vm(vm=vm_static, enable_ssh=False)


@pytest.fixture(scope="module")
def running_vm_for_migration(vm_for_migration):
    return running_vm(vm=vm_for_migration, enable_ssh=False)


@pytest.fixture()
def migrated_vmi(running_vm_for_migration):
    LOGGER.info(
        f"Migrating {running_vm_for_migration.name}. Current node: "
        f"{running_vm_for_migration.vmi.node.name}"
    )

    ip_before = running_vm_for_migration.vmi.interfaces[0]["ipAddress"]
    migrated_vmi = migrate_vm_and_verify(
        vm=running_vm_for_migration, wait_for_migration_success=False
    )

    for sample in TimeoutSampler(
        wait_timeout=60,
        sleep=1,
        func=lambda: ip_before
        != running_vm_for_migration.vmi.interfaces[0]["ipAddress"],
    ):
        if sample:
            break

    yield
    migrated_vmi.clean_up()


@pytest.fixture(scope="module")
def vm_console_connection_ready(running_vm_for_migration):
    wait_for_console(
        vm=running_vm_for_migration,
        console_impl=console.Fedora,
    )


@pytest.mark.polarion("CNV-6733")
def test_connectivity_after_migration(
    skip_when_one_node,
    namespace,
    running_vm_static,
    running_vm_for_migration,
    migrated_vmi,
    vm_console_connection_ready,
):
    """
    test for connectivity of a migrated vm with masquerade.
    using console to ping from migrated_vmi to running_vm_static.
    It is important to connect using console and not ssh because connecting
    through ssh hides the bug.
    The ping should take place right after vm_for_migration is migrated to
    the new node.
    the ping command include '-c 10 -w 10' so that in case there is a packet
    loss the exit code will be 1 and not 0.
    """
    LOGGER.info(
        f"pinging from migrated {running_vm_for_migration.name} to "
        f"{running_vm_static.name}"
    )
    static_vm_ip = running_vm_static.vmi.interfaces[0]["ipAddress"]

    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=running_vm_for_migration,
        commands=[f"ping {static_vm_ip} -c 10 -w 10"],
        timeout=10,
    )