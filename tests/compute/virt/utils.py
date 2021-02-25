import logging
from contextlib import contextmanager

from resources.node import Node
from resources.utils import TimeoutSampler

from utilities.infra import run_ssh_commands
from utilities.virt import kubernetes_taint_exists


LOGGER = logging.getLogger(__name__)


class NodeMaintenanceException(Exception):
    def __init__(self, node, action, error):
        self.node = node
        self.action = action
        self.error = error

    def __str__(self):
        return f"{self.action} node maintenance failed: {self.node.name} - {self.error}"


def wait_for_node_schedulable_status(node, status, timeout=60):
    """
    Wait for node status to be ready (status=True) or unschedulable (status=False)
    """
    LOGGER.info(
        f"Wait for node {node.name} to be {Node.Status.READY if status else Node.Status.SCHEDULING_DISABLED}."
    )

    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=1,
        func=node.api().get,
        label_selector=f"kubernetes.io/hostname={node.name}",
    )
    for sample in sampler:
        if sample.items:
            if status:
                if not sample.items[
                    0
                ].spec.unschedulable and not kubernetes_taint_exists(node):
                    return
            else:
                if sample.items[0].spec.unschedulable and kubernetes_taint_exists(node):
                    return


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
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=["bash", "-c", f"/usr/bin/pidof '{process_name}' || true"],
    )[0]
    pid = output.strip()
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
