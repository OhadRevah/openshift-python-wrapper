from ocp_resources.utils import TimeoutSampler

from utilities.constants import TIMEOUT_2MIN
from utilities.infra import get_pod_by_name_prefix


NON_EXISTS_IMAGE = "non-exists-image-test-cnao-alerts"


def wait_for_kubemacpool_pods_error_state(dyn_client, hco_namespace):
    kubemacpoolpods = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=get_pod_by_name_prefix,
        dyn_client=dyn_client,
        pod_prefix="kubemacpool",
        namespace=hco_namespace.name,
        get_all=True,
    )
    for macpool in kubemacpoolpods:
        if {pod.status for pod in macpool} == {"Pending"}:
            return
