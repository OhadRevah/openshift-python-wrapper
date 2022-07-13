import logging

import pytest
from ocp_resources.utils import TimeoutSampler
from pytest_testconfig import py_config

from tests.storage.upgrade.utils import (
    create_snapshot_for_upgrade,
    create_vm_for_snapshot_upgrade_tests,
)
from utilities.constants import HOTPLUG_DISK_SERIAL
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import create_dv, virtctl_volume
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    wait_for_ssh_connectivity,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def skip_if_less_than_two_storage_classes(cluster_storage_classes):
    if len(cluster_storage_classes) < 2:
        pytest.skip(msg="Need two Storage Classes at least.")


@pytest.fixture(scope="session")
def storage_class_for_updating_cdiconfig_scratch(
    skip_if_less_than_two_storage_classes, cdi_config, cluster_storage_classes
):
    """
    Choose one StorageClass which is not the current one for scratch space.
    """
    current_sc_for_scratch = cdi_config.scratch_space_storage_class_from_status
    LOGGER.info(
        f"The current StorageClass for scratch space on CDIConfig is: {current_sc_for_scratch}"
    )
    for sc in cluster_storage_classes:
        if sc.instance.metadata.get("name") != current_sc_for_scratch:
            LOGGER.info(f"Candidate StorageClass: {sc.instance.metadata.name}")
            return sc


@pytest.fixture(scope="session")
def override_cdiconfig_scratch_spec(
    hyperconverged_resource_scope_session,
    cdi_config,
    storage_class_for_updating_cdiconfig_scratch,
):
    """
    Change spec.scratchSpaceStorageClass to the selected StorageClass on CDIConfig.
    """
    if storage_class_for_updating_cdiconfig_scratch:
        new_sc = storage_class_for_updating_cdiconfig_scratch.name

        def _wait_for_sc_update():
            samples = TimeoutSampler(
                wait_timeout=30,
                sleep=1,
                func=lambda: cdi_config.scratch_space_storage_class_from_status
                == new_sc,
            )
            for sample in samples:
                if sample:
                    return

        with ResourceEditorValidateHCOReconcile(
            patches={
                hyperconverged_resource_scope_session: {
                    "spec": {"scratchSpaceStorageClass": new_sc}
                }
            },
        ) as edited_cdi_config:
            _wait_for_sc_update()

            yield edited_cdi_config


@pytest.fixture(scope="session")
def skip_if_not_override_cdiconfig_scratch_space(override_cdiconfig_scratch_spec):
    if not override_cdiconfig_scratch_spec:
        pytest.skip(msg="Skip test because the scratch space was not changed.")


@pytest.fixture(scope="session")
def cirros_vm_for_upgrade_a(upgrade_namespace_scope_session, admin_client):
    with create_vm_for_snapshot_upgrade_tests(
        vm_name="snapshot-upgrade-a",
        namespace=upgrade_namespace_scope_session.name,
        client=admin_client,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def snapshots_for_upgrade_a(
    admin_client,
    cirros_vm_for_upgrade_a,
):
    with create_snapshot_for_upgrade(
        vm=cirros_vm_for_upgrade_a, client=admin_client
    ) as snapshot:
        yield snapshot


@pytest.fixture(scope="session")
def cirros_vm_for_upgrade_b(upgrade_namespace_scope_session, admin_client):
    with create_vm_for_snapshot_upgrade_tests(
        vm_name="snapshot-upgrade-b",
        namespace=upgrade_namespace_scope_session.name,
        client=admin_client,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def snapshots_for_upgrade_b(
    admin_client,
    cirros_vm_for_upgrade_b,
):
    with create_snapshot_for_upgrade(
        vm=cirros_vm_for_upgrade_b, client=admin_client
    ) as snapshot:
        yield snapshot


@pytest.fixture(scope="session")
def blank_disk_dv_with_default_sc(upgrade_namespace_scope_session):
    with create_dv(
        source="blank",
        dv_name="blank-dv",
        namespace=upgrade_namespace_scope_session.name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.fixture(scope="session")
def fedora_vm_for_hotplug_upg(upgrade_namespace_scope_session):
    name = "fedora-hotplug-upg"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_namespace_scope_session.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="session")
def hotplug_volume_upg(fedora_vm_for_hotplug_upg):
    with virtctl_volume(
        action="add",
        namespace=fedora_vm_for_hotplug_upg.namespace,
        vm_name=fedora_vm_for_hotplug_upg.name,
        volume_name="blank-dv",
        persist=True,
        serial=HOTPLUG_DISK_SERIAL,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.fixture()
def fedora_vm_for_hotplug_upg_ssh_connectivity(fedora_vm_for_hotplug_upg):
    wait_for_ssh_connectivity(vm=fedora_vm_for_hotplug_upg)
