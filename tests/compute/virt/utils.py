import logging

from resources.node import Node
from resources.utils import TimeoutSampler
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
        timeout=timeout,
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
