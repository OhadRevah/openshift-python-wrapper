import logging

from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.hyperconverged import HyperConverged
from resources.resource import Resource
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_10MIN


DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
DEFAULT_HCO_PROGRESSING_CONDITIONS = {
    Resource.Condition.PROGRESSING: Resource.Condition.Status.TRUE,
}
LOGGER = logging.getLogger(__name__)


def wait_for_hco_conditions(
    admin_client,
    conditions=DEFAULT_HCO_CONDITIONS,
    sleep=5,
    # number_of_consecutive_checks is the number of time to repeat the status check to make sure the
    # transition is done. In some case we can get into situation when a ready status is because the
    # process was not start yet, or part of the component are ready but others didn't start the process
    # yet. In these case we'll use a higher value in number_of_consecutive_checks to make sure the ready
    # status is consistence.
    number_of_consecutive_checks=1,
):
    """
    Checking HCO conditions.
    If conditions are not met in the given time Raise TimeoutExpiredError.
    """
    expected_hco_conditions = conditions

    actual_hco_conditions = {}
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=sleep,
        func=lambda: list(
            HyperConverged.get(
                dyn_client=admin_client, namespace=py_config["hco_namespace"]
            )
        ),
        exceptions=NotFoundError,
    )
    current_check = 0
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
                    current_check = current_check + 1
                    if current_check >= number_of_consecutive_checks:
                        return
                else:
                    current_check = 0

    except TimeoutExpiredError:
        LOGGER.error(
            f"Expected conditions: {expected_hco_conditions}. Actual "
            f"conditions: {actual_hco_conditions}"
        )
        raise
