from utilities import utils

KUBEVIRT_TAINT = "kubevirt.io/drain"
K8S_TAINT = "node.kubernetes.io/unschedulable"
NO_SCHEDULE = "NoSchedule"


class NodeMaintenanceException(Exception):
    def __init__(self, node, action, error):
        self.node = node
        self.action = action
        self.error = error

    def __str__(self):
        return f"{self.action} node maintenance failed: {self.node.name} - {self.error}"


def wait_for_node_unschedulable_status(node, status, timeout=30):
    sampler = utils.TimeoutSampler(
        timeout=timeout,
        sleep=1,
        func=node.api().get,
        label_selector=f"kubernetes.io/hostname={node.name}",
    )
    for sample in sampler:
        if sample.items:
            if status:
                if (
                    sample.items[0].spec.unschedulable
                    and _kubevirt_taint_exists(node)
                    and _kubernetes_taint_exists(node)
                ):
                    return
            else:
                if (
                    not sample.items[0].spec.unschedulable
                    and not _kubevirt_taint_exists(node)
                    and not _kubernetes_taint_exists(node)
                ):
                    return


def _kubevirt_taint_exists(node):
    taints = node.instance.spec.taints
    if taints:
        return any(
            taint.key == KUBEVIRT_TAINT and taint.effect == NO_SCHEDULE
            for taint in taints
        )


def _kubernetes_taint_exists(node):
    taints = node.instance.spec.taints
    if taints:
        return any(
            taint.key == K8S_TAINT and taint.effect == NO_SCHEDULE for taint in taints
        )
