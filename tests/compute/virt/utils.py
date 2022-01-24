import logging
from contextlib import contextmanager

from tests.compute.utils import (
    fetch_processid_from_linux_vm,
    update_hco_annotations,
    wait_for_updated_kv_value,
)
from utilities.infra import run_ssh_commands


LOGGER = logging.getLogger(__name__)


class NodeMaintenanceException(Exception):
    def __init__(self, node, action, error):
        self.node = node
        self.action = action
        self.error = error

    def __str__(self):
        return f"{self.action} node maintenance failed: {self.node.name} - {self.error}"


def assert_process_not_running(vm, process):
    assert "1" in run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "bash",
            "-c",
            f"/usr/bin/ps aux | grep '{process}'| grep -v grep | wc -l",
        ],
    )[0]


def kill_running_process(vm, process):
    process_name = process.split()[0]
    pid = fetch_processid_from_linux_vm(vm=vm, process_name=process_name).strip()
    if pid:
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=["bash", "-c", f"kill '{pid}'"],
        )


@contextmanager
def running_sleep_in_linux(vm):
    process = "/usr/bin/sleep 1000"
    kill_running_process(vm=vm, process=process)
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=["nohup", "bash", "-c", f"{process} >& /dev/null &", "&"],
    )
    assert_process_not_running(vm=vm, process=process)
    yield
    assert_process_not_running(vm=vm, process=process)
    kill_running_process(vm=vm, process=process)


@contextmanager
def append_feature_gate_to_hco(feature_gate, resource, client, namespace):
    with update_hco_annotations(
        resource=resource,
        path="developerConfiguration/featureGates",
        value=feature_gate,
    ):
        wait_for_updated_kv_value(
            admin_client=client,
            hco_namespace=namespace,
            path=[
                "developerConfiguration",
                "featureGates",
            ],
            value=feature_gate,
        )
        yield
