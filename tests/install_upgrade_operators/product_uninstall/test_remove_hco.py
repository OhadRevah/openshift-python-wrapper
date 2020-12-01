import logging
from datetime import datetime

import pytest
from pytest_testconfig import config as py_config
from resources.event import Event
from resources.hyperconverged import HyperConverged

from utilities.virt import VirtualMachineForTests, fedora_vm_body


HCO_DEPLOY_TIMEOUT = 5 * 60
LOGGER = logging.getLogger(__name__)
DV_PARAMS = {
    "source": "blank",
    "dv_name": "remove-hco-dv",
    "image": "",
    "dv_size": "64Mi",
    "storage_class": py_config["default_storage_class"],
}
VIRT_EVENT = "ErrVirtUninstall"
CDI_EVENT = "ErrCDIUninstall"


@pytest.fixture()
def hyperconverged_resource(admin_client):
    for hco in HyperConverged.get(dyn_client=admin_client):
        return hco


@pytest.fixture(scope="module")
def remove_hco_vm(unprivileged_client, namespace):
    name = "remove-hco-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        teardown=False,
    ) as vm:
        vm.start(timeout=300)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def delete_events_before_test(admin_client):
    Event.delete_events(
        dyn_client=admin_client,
        namespace=py_config["hco_namespace"],
        field_selector=f"reason={VIRT_EVENT}",
    )
    Event.delete_events(
        dyn_client=admin_client,
        namespace=py_config["hco_namespace"],
        field_selector=f"reason={CDI_EVENT}",
    )


@pytest.fixture(scope="module")
def start_time():
    yield f"{datetime.utcnow().isoformat(timespec='seconds')}Z"


@pytest.mark.destructive
@pytest.mark.parametrize(
    "data_volume_scope_class",
    [pytest.param(DV_PARAMS)],
    indirect=True,
)
class TestRemoveHCO:
    @pytest.mark.polarion("CNV-3916")
    def test_block_removal(
        self,
        admin_client,
        delete_events_before_test,
        hyperconverged_resource,
        remove_hco_vm,
        data_volume_scope_class,
        start_time,
    ):
        """
        testcase to verify that HCO can really not be deleted when VMs and/or DVs are still defined.

        test plan:

         1. create a VM (vm fixture)
         2. create an additional DV (data_volume fixture)
         3. delete HCO CR
         4. check that HCO CR is still there pending for deletion
         5. check that we have an event on the CSV object to alert the user
         6. delete the VM
         7. check that HCO CR is still there
         8. delete the DV
         9. check that HCO CR and all the other CNV related CRs are gone

         After the test:
         Restore HCO after deletion
        """
        LOGGER.info(f"HCO deletion time (UTC): {start_time}")

        hyperconverged_resource.delete()  # (3) delete HCO CR

        # (4) Make sure HCO exists, but waiting for deletion
        metadata = hyperconverged_resource.instance["metadata"]
        assert (
            hyperconverged_resource.exists
            and metadata.get("deletionTimestamp") is not None
            and remove_hco_vm.exists
            and remove_hco_vm.vmi.status == remove_hco_vm.vmi.Status.RUNNING
            and data_volume_scope_class.exists
        )

        # (5) check that there is a warning event
        ok, msg = assert_event(
            dyn_client=admin_client,
            event_reason=VIRT_EVENT,
            start_time=start_time,
        )
        assert ok, msg

    @pytest.mark.run(after="test_block_removal")
    @pytest.mark.polarion("CNV-4044")
    def test_remove_vm(
        self, remove_hco_vm, hyperconverged_resource, data_volume_scope_class
    ):
        # (6) delete the VM
        remove_hco_vm.delete(wait=True)

        # (7) check that HCO still not deleted
        assert (
            hyperconverged_resource.exists
            and not remove_hco_vm.exists
            and data_volume_scope_class.exists
        )

    @pytest.mark.run(after="test_remove_vm")
    @pytest.mark.polarion("CNV-4098")
    def test_assert_event_dv(
        self, admin_client, kubevirt_resource, start_time, data_volume_scope_class
    ):
        kubevirt_resource.wait_deleted()
        ok, msg = assert_event(
            dyn_client=admin_client, event_reason=CDI_EVENT, start_time=start_time
        )
        assert ok, msg

    @pytest.mark.run(after="test_assert_event_dv")
    @pytest.mark.polarion("CNV-4045")
    def test_remove_dv(self, data_volume_scope_class, hyperconverged_resource):
        # (8) delete the DV
        data_volume_scope_class.delete(wait=True)
        assert not data_volume_scope_class.exists

        # (9) HCO should be deleted now, after the VM and the DV are gone. Just wait for it to happen
        if hyperconverged_resource is not None and hyperconverged_resource.exists:
            hyperconverged_resource.wait_deleted()

    # Restore HCO for the next tests
    @pytest.mark.run(after="test_remove_dv")
    @pytest.mark.polarion("CNV-4093")
    def test_restore_hco(self, admin_client, data_volume_scope_class):

        LOGGER.info("Recreating HCO")
        with HyperConverged(
            name="kubevirt-hyperconverged",
            namespace=py_config["hco_namespace"],
            client=admin_client,
            teardown=False,
        ) as hco:
            LOGGER.info("Waiting for all HCO conditions to detect that it is deployed")
            assert hco.exists
            hco.wait_for_condition(
                condition=HyperConverged.Condition.PROGRESSING,
                status=HyperConverged.Condition.Status.FALSE,
                timeout=HCO_DEPLOY_TIMEOUT,
            )
            hco.wait_for_condition(
                condition=HyperConverged.Condition.DEGRADED,
                status=HyperConverged.Condition.Status.FALSE,
            )
            hco.wait_for_condition(
                condition=HyperConverged.Condition.AVAILABLE,
                status=HyperConverged.Condition.Status.TRUE,
                timeout=HCO_DEPLOY_TIMEOUT,
            )
            hco.wait_for_condition(
                condition=HyperConverged.Condition.UPGRADEABLE,
                status=HyperConverged.Condition.Status.TRUE,
            )


# assert that a certain event was emitted
def assert_event(dyn_client, event_reason, start_time):
    for event in Event.get(
        dyn_client,
        namespace=py_config["hco_namespace"],
        field_selector=f"involvedObject.kind==ClusterServiceVersion,type==Warning,reason={event_reason}",
        timeout=10,
    ):
        event_time = event["object"]["lastTimestamp"]
        LOGGER.debug(
            f'event time: {event_time}, event reason: {event["object"]["reason"]}'
        )
        # skip old events
        if event_time < start_time:
            continue

        # found at least one event - exit with no assertion error
        return True, None

    return False, f"missing {event_reason} event"
