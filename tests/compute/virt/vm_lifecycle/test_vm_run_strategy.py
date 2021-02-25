# -*- coding: utf-8 -*-

# Run strategies logic can be found under
# https://kubevirt.io/user-guide/#/creation/run-strategies?id=run-strategies

import logging
import re
import shlex

import pytest
from kubernetes.client.rest import ApiException
from resources.resource import ResourceEditor
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachine, VirtualMachineInstance

from utilities.constants import TIMEOUT_10MIN
from utilities.infra import run_ssh_commands
from utilities.virt import migrate_and_verify, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)

MANUAL = VirtualMachine.RunStrategy.MANUAL
ALWAYS = VirtualMachine.RunStrategy.ALWAYS
HALTED = VirtualMachine.RunStrategy.HALTED
RERUNONFAILURE = VirtualMachine.RunStrategy.RERUNONFAILURE

RUN_STRATEGY_DICT = {
    MANUAL: {
        "start": {"status": True, "run_strategy": MANUAL},
        "restart": {"status": True, "run_strategy": MANUAL},
        "stop": {"status": None, "run_strategy": MANUAL},
    },
    ALWAYS: {
        "start": {
            "status": True,
            "run_strategy": ALWAYS,
            "expected_exceptions": [
                ".*Always does not support manual start requests.*",
                ".*VM is already running.*",
            ],
        },
        "restart": {"status": True, "run_strategy": ALWAYS},
        "stop": {"status": None, "run_strategy": HALTED},
    },
    HALTED: {
        "start": {"status": True, "run_strategy": ALWAYS},
        "restart": {"status": True, "run_strategy": ALWAYS},
        "stop": {"status": None, "run_strategy": HALTED},
    },
    RERUNONFAILURE: {
        "start": {
            "status": True,
            "run_strategy": RERUNONFAILURE,
            "expected_exceptions": [
                ".*RerunOnFailure does not support starting VM from failed state.*",
                ".*VM is already running.*",
            ],
        },
        "restart": {
            "status": True,
            "run_strategy": RERUNONFAILURE,
        },
        "stop": {
            "status": None,
            "run_strategy": HALTED,
            "expected_exception": "VM is not running",
        },
    },
}

# expected statuses for vm and vmi crs after shutdown from inside vm
RUN_STRATEGY_SHUTDOWN_STATUS = {
    MANUAL: {
        "vmi": "Succeeded",
        "launcher_pod": "Succeeded",
    },
    RERUNONFAILURE: {
        "vmi": "Succeeded",
        "launcher_pod": "Succeeded",
    },
    ALWAYS: {"vmi": "Running", "launcher_pod": "Running"},
}


@pytest.fixture()
def skip_containerdisk_vm(lifecycle_vm):
    if [
        True
        for volume in lifecycle_vm.instance.spec.template.spec.volumes
        if volume.get("containerDisk")
    ]:
        pytest.skip("Skip test for VM using container disk.")


@pytest.fixture()
def skip_run_strategy_halted(run_strategy_matrix__class__):
    if run_strategy_matrix__class__ == HALTED:
        pytest.skip("Skip test for VM with Halted runStrategy")


def updated_vm_run_strategy(run_strategy, vm_for_test):
    LOGGER.info(f"Update VM with runStrategy {run_strategy}")

    if (
        vm_for_test.vmi.exists
        and vm_for_test.vmi.status == VirtualMachineInstance.Status.RUNNING
    ):
        vm_for_test.stop(wait=True)

    ResourceEditor(
        patches={vm_for_test: {"spec": {"runStrategy": run_strategy}}}
    ).update()
    return run_strategy


@pytest.fixture(scope="class")
def matrix_updated_vm_run_strategy(run_strategy_matrix__class__, lifecycle_vm):
    # Update the VM run strategy from run_strategy_matrix__class__
    return updated_vm_run_strategy(
        run_strategy=run_strategy_matrix__class__, vm_for_test=lifecycle_vm
    )


@pytest.fixture()
def request_updated_vm_run_strategy(request, lifecycle_vm):
    # Update the VM run strategy from request.param
    return updated_vm_run_strategy(
        run_strategy=request.param["run_strategy"], vm_for_test=lifecycle_vm
    )


@pytest.fixture()
def start_vm_if_not_running(lifecycle_vm):

    vm_run_strategy = lifecycle_vm.instance.spec.runStrategy

    if not lifecycle_vm.ready:
        # runStrategy policy acc. to vm's current run strategy
        run_strategy_policy = RUN_STRATEGY_DICT[vm_run_strategy]["start"]
        LOGGER.info(f"Starting VM {lifecycle_vm.name}")
        run_vm_action(
            vm=lifecycle_vm,
            vm_action="start",
            expected_exceptions=run_strategy_policy.get("expected_exceptions"),
        )

    lifecycle_vm.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=lifecycle_vm.vmi)


@pytest.fixture(scope="module")
def stop_vm_if_running(lifecycle_vm):
    # Tests should start with a stopped VM
    if lifecycle_vm.ready:
        lifecycle_vm.stop(wait=True)


def run_vm_action(vm, vm_action, expected_exceptions=None):
    LOGGER.info(f"{vm_action} VM")

    def _vm_run_action():
        if expected_exceptions:
            # when runStrategy changes cause a VM to start and then we immediately
            # send the start instruction from here there is a race condition which may
            # cause expected exceptions not to be raised.
            try:
                getattr(vm, vm_action)(wait=True, timeout=TIMEOUT_10MIN)
            except ApiException as e:
                if re.search(
                    pattern=rf"{'|'.join(expected_exceptions)}", string=str(e)
                ):
                    return True
                raise e
        else:
            getattr(vm, vm_action)(wait=True, timeout=TIMEOUT_10MIN)
            return True

    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=2,
        func=_vm_run_action,
    ):
        if sample:
            break


def verify_vm_vmi_status(vm, ready):
    LOGGER.info(f"Verify VMI status: {ready}")
    vm.wait_for_status(status=ready, timeout=TIMEOUT_10MIN)
    if ready:
        vm.vmi.wait_for_status(status=VirtualMachineInstance.Status.RUNNING)


def verify_vm_run_strategy(vm, run_strategy):
    LOGGER.info(f"Verify VM runStrategy: {run_strategy}")
    assert vm.instance.spec.runStrategy == run_strategy


def verify_vm_action(vm, vm_action, run_strategy):
    run_strategy_policy = RUN_STRATEGY_DICT[run_strategy][vm_action]
    run_vm_action(
        vm=vm,
        vm_action=vm_action,
        expected_exceptions=run_strategy_policy.get("expected_exceptions"),
    )
    verify_vm_vmi_status(vm=vm, ready=run_strategy_policy["status"])
    verify_vm_run_strategy(vm=vm, run_strategy=run_strategy_policy["run_strategy"])


def pause_unpause_vmi_and_verify_status(vm):
    vm.vmi.pause(wait=True)
    verify_vm_vmi_status(vm=vm, ready=True)
    vm.vmi.unpause(wait=True)
    verify_vm_vmi_status(vm=vm, ready=True)


@pytest.mark.usefixtures("stop_vm_if_running")
class TestRunStrategy:
    @pytest.mark.parametrize(
        "vm_action",
        [
            pytest.param("start", marks=pytest.mark.polarion("CNV-4685")),
            pytest.param("restart", marks=pytest.mark.polarion("CNV-4686")),
            pytest.param("stop", marks=pytest.mark.polarion("CNV-4687")),
        ],
    )
    @pytest.mark.first
    def test_run_strategy_policy(
        self,
        lifecycle_vm,
        matrix_updated_vm_run_strategy,
        vm_action,
    ):
        LOGGER.info(
            f"Verify VM with run strategy {matrix_updated_vm_run_strategy} and VM action {vm_action}"
        )
        verify_vm_action(
            vm=lifecycle_vm,
            vm_action=vm_action,
            run_strategy=matrix_updated_vm_run_strategy,
        )

    @pytest.mark.polarion("CNV-5054")
    def test_run_strategy_shutdown(
        self,
        lifecycle_vm,
        skip_run_strategy_halted,
        matrix_updated_vm_run_strategy,
        start_vm_if_not_running,
    ):
        vmi = lifecycle_vm.vmi
        launcher_pod = vmi.virt_launcher_pod
        run_strategy = matrix_updated_vm_run_strategy
        status = RUN_STRATEGY_SHUTDOWN_STATUS[run_strategy]

        # send poweroff
        run_ssh_commands(
            host=lifecycle_vm.ssh_exec, commands=shlex.split("sudo poweroff")
        )

        # runStrategy "Always" first terminates the pod, then re-raises it
        # The other two runStrategies go directly to completed
        if run_strategy == ALWAYS:
            launcher_pod.wait_deleted()

        # wait for vmi and launcher pod status by matrix
        vmi.wait_for_status(status=status["vmi"])
        vmi.virt_launcher_pod.wait_for_status(status=status["launcher_pod"])


@pytest.mark.parametrize(
    "request_updated_vm_run_strategy",
    [
        pytest.param(
            {"run_strategy": MANUAL},
            marks=pytest.mark.polarion("CNV-4688"),
            id="Manual",
        ),
        pytest.param(
            {"run_strategy": ALWAYS},
            marks=pytest.mark.polarion("CNV-4689"),
            id="Always",
        ),
    ],
    indirect=True,
)
def test_run_strategy_pause_unpause_vmi(
    lifecycle_vm, request_updated_vm_run_strategy, start_vm_if_not_running
):
    LOGGER.info(
        f"Verify VMI pause/un-pause with runStrategy: {request_updated_vm_run_strategy}"
    )
    pause_unpause_vmi_and_verify_status(vm=lifecycle_vm)


@pytest.mark.parametrize(
    "request_updated_vm_run_strategy",
    [
        pytest.param(
            {"run_strategy": ALWAYS},
            marks=pytest.mark.polarion("CNV-4690"),
            id="Always",
        )
    ],
    indirect=True,
)
def test_always_run_migrate_vm(
    skip_upstream, skip_containerdisk_vm, lifecycle_vm, request_updated_vm_run_strategy
):
    LOGGER.info("The VM migration with runStrategy 'Always'")
    verify_vm_vmi_status(vm=lifecycle_vm, ready=True)
    migrate_and_verify(vm=lifecycle_vm)
    verify_vm_vmi_status(vm=lifecycle_vm, ready=True)
    verify_vm_run_strategy(vm=lifecycle_vm, run_strategy=ALWAYS)
