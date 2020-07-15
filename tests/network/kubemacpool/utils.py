import logging

from resources.pod import Pod
from resources.utils import TimeoutExpiredError, TimeoutSampler


LOGGER = logging.getLogger(__name__)
KMP_PODS_LABEL = "control-plane=mac-controller-manager"


def get_pods(dyn_client, namespace, label=None):
    return list(
        Pod.get(dyn_client=dyn_client, namespace=namespace.name, label_selector=label,)
    )


def wait_for_kmp_pods_creation(dyn_client, namespace, replicas):
    samples = TimeoutSampler(
        timeout=120,
        sleep=1,
        func=get_pods,
        dyn_client=dyn_client,
        namespace=namespace,
        label=KMP_PODS_LABEL,
    )
    for sample in samples:
        if len(sample) == replicas:
            return


def wait_for_pods_deletion(pods):
    for pod in pods:
        pod.wait_deleted()


def wait_for_kmp_pods_to_be_in_crashloop(dyn_client, namespace):
    for pod in get_pods(
        dyn_client=dyn_client, namespace=namespace, label=KMP_PODS_LABEL
    ):
        LOGGER.info(
            f"Wait for {pod.name} container status to be {Pod.Status.CRASH_LOOPBACK_OFF}"
        )
        pod_states = TimeoutSampler(
            timeout=30,
            sleep=1,
            func=lambda: pod.instance.status.containerStatuses[0].state,
        )
        try:
            for pod_state in pod_states:
                if pod_state.waiting:
                    if pod_state.waiting.reason == Pod.Status.CRASH_LOOPBACK_OFF:
                        break
        except TimeoutExpiredError:
            LOGGER.error(
                f"{pod.name} container did not get status {Pod.Status.CRASH_LOOPBACK_OFF}"
            )
            raise
