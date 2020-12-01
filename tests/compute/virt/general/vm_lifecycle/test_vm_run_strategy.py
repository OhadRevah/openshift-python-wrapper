# -*- coding: utf-8 -*-

# Run strategies logic can be found under
# https://kubevirt.io/user-guide/#/creation/run-strategies?id=run-strategies

import logging
import re
from contextlib import contextmanager

import pytest
from kubernetes.client.rest import ApiException
from pexpect import EOF
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.resource import ResourceEditor
from resources.template import Template
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachine, VirtualMachineInstance

from tests.compute.utils import migrate_vm
from utilities import console
from utilities.storage import create_dv, get_images_external_http_server
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


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


@contextmanager
def container_disk_vm(namespace, unprivileged_client):
    name = "fedora-vm-run-strategy"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        run_strategy=MANUAL,
    ) as vm:
        yield vm


@contextmanager
def data_volume_vm(unprivileged_client, namespace):
    with create_dv(
        dv_name="fedora-dv-run-strategy",
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{py_config['latest_fedora_version']['image_path']}",
        storage_class=py_config["default_storage_class"],
        access_modes=py_config["default_access_mode"],
        volume_mode=py_config["default_volume_mode"],
        size=py_config["latest_fedora_version"]["dv_size"],
    ) as dv:
        # wait for dv import to start and complete
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=1800)

        with VirtualMachineForTestsFromTemplate(
            name="fedora-vm-run-strategy",
            namespace=dv.namespace,
            client=unprivileged_client,
            labels=Template.generate_template_labels(
                **py_config["latest_fedora_version"]["template_labels"]
            ),
            data_volume=dv,
            run_strategy=MANUAL,
        ) as vm:
            yield vm


@pytest.fixture(scope="module")
def vm_for_test(unprivileged_client, namespace, vm_volumes_matrix__module__):
    """Wrapper fixture to generate the desired VM
    vm_volumes_matrix returns a string.
    globals() is used to call the actual contextmanager with that name
    """
    with globals()[vm_volumes_matrix__module__](
        unprivileged_client=unprivileged_client, namespace=namespace
    ) as vm:
        yield vm


@pytest.fixture()
def skip_containerdisk_vm(vm_for_test):
    if [
        True
        for volume in vm_for_test.instance.spec.template.spec.volumes
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
def matrix_updated_vm_run_strategy(run_strategy_matrix__class__, vm_for_test):
    # Update the VM run strategy from run_strategy_matrix__class__
    return updated_vm_run_strategy(
        run_strategy=run_strategy_matrix__class__, vm_for_test=vm_for_test
    )


@pytest.fixture()
def request_updated_vm_run_strategy(request, vm_for_test):
    # Update the VM run strategy from request.param
    return updated_vm_run_strategy(
        run_strategy=request.param["run_strategy"], vm_for_test=vm_for_test
    )


@pytest.fixture()
def start_vm_if_not_running(vm_for_test, matrix_updated_vm_run_strategy):
    if not vm_for_test.ready:
        run_strategy_policy = RUN_STRATEGY_DICT[matrix_updated_vm_run_strategy]["start"]
        LOGGER.info(f"Starting VM {vm_for_test.name}")
        run_vm_action(
            vm=vm_for_test,
            vm_action="start",
            expected_exceptions=run_strategy_policy.get("expected_exceptions"),
        )

    vm_for_test.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vm_for_test.vmi)


def run_vm_action(vm, vm_action, expected_exceptions=None):
    LOGGER.info(f"{vm_action} VM")

    def _vm_run_action():
        if expected_exceptions:
            # when runStrategy changes cause a VM to start and then we immediately
            # send the start instruction from here there is a race condition which may
            # cause expected exceptions not to be raised.
            try:
                getattr(vm, vm_action)(wait=True)
            except ApiException as e:
                if re.search(
                    pattern=rf"{'|'.join(expected_exceptions)}", string=str(e)
                ):
                    return True
                raise e
        else:
            getattr(vm, vm_action)(wait=True)
            return True

    for sample in TimeoutSampler(
        timeout=300,
        sleep=2,
        func=_vm_run_action,
    ):
        if sample:
            break


def verify_vm_vmi_status(vm, ready):
    LOGGER.info(f"Verify VM/I status: {ready}")
    vm.wait_for_status(status=ready)
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
        vm_for_test,
        matrix_updated_vm_run_strategy,
        vm_action,
    ):
        LOGGER.info(
            f"Verify VM with run strategy {matrix_updated_vm_run_strategy} and VM action {vm_action}"
        )
        verify_vm_action(
            vm=vm_for_test,
            vm_action=vm_action,
            run_strategy=matrix_updated_vm_run_strategy,
        )

    @pytest.mark.polarion("CNV-5054")
    def test_run_strategy_shutdown(
        self,
        vm_for_test,
        skip_run_strategy_halted,
        matrix_updated_vm_run_strategy,
        start_vm_if_not_running,
    ):
        vmi = vm_for_test.vmi
        launcher_pod = vmi.virt_launcher_pod
        run_strategy = matrix_updated_vm_run_strategy
        status = RUN_STRATEGY_SHUTDOWN_STATUS[run_strategy]

        # send poweroff
        with pytest.raises(EOF):
            with console.Fedora(vm=vm_for_test, timeout=600) as vm_console:
                vm_console.sendline(s="sudo poweroff")

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
        ),
        pytest.param(
            {"run_strategy": ALWAYS},
            marks=pytest.mark.polarion("CNV-4689"),
        ),
    ],
    indirect=True,
)
def test_run_strategy_pause_unpause_vmi(
    vm_for_test, request_updated_vm_run_strategy, start_vm_if_not_running
):
    LOGGER.info(
        f"Verify VMI pause/un-pause with runStrategy: {request_updated_vm_run_strategy}"
    )
    pause_unpause_vmi_and_verify_status(vm=vm_for_test)


@pytest.mark.parametrize(
    "request_updated_vm_run_strategy",
    [
        pytest.param(
            {"run_strategy": ALWAYS},
            marks=pytest.mark.polarion("CNV-4690"),
        )
    ],
    indirect=True,
)
def test_always_run_migrate_vm(
    skip_upstream, skip_containerdisk_vm, vm_for_test, request_updated_vm_run_strategy
):
    LOGGER.info("The VM migration with runStrategy 'Always'")
    verify_vm_vmi_status(vm=vm_for_test, ready=True)
    migrate_vm(vm=vm_for_test)
    verify_vm_vmi_status(vm=vm_for_test, ready=True)
    verify_vm_run_strategy(vm=vm_for_test, run_strategy=ALWAYS)
