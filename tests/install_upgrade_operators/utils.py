import logging

from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.hyperconverged import HyperConverged
from resources.resource import Resource
from resources.utils import TimeoutExpiredError, TimeoutSampler


DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
LOGGER = logging.getLogger(__name__)


def wait_for_hco_conditions(admin_client, conditions=DEFAULT_HCO_CONDITIONS):
    """
    Checking HCO conditions.
    If conditions are not met in the given time Raise TimeoutExpiredError.
    """
    expected_hco_conditions = conditions

    actual_hco_conditions = {}
    samples = TimeoutSampler(
        timeout=600,
        sleep=5,
        func=lambda: list(
            HyperConverged.get(
                dyn_client=admin_client, namespace=py_config["hco_namespace"]
            )
        ),
        exceptions=NotFoundError,
    )

    try:
        for sample in samples:
            if sample:
                resource_conditions = sample[0].instance.status.conditions
                actual_hco_conditions = {
                    condition.type: condition.status
                    for condition in resource_conditions
                    if condition.type in expected_hco_conditions.keys()
                }

                if actual_hco_conditions == expected_hco_conditions:
                    return

    except TimeoutExpiredError:
        LOGGER.error(
            f"Expected conditions: {expected_hco_conditions}. Actual "
            f"conditions: {actual_hco_conditions}"
        )
        raise
