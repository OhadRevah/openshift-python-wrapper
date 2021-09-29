import logging

from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)


VALID_PRIORITY_CLASS = [
    "openshift-user-critical",
    "system-cluster-critical",
    "system-node-critical",
    "kubevirt-cluster-critical",
]

LOGGER = logging.getLogger(__name__)


# TODO: remove this function when all the pod related bugs for missing spec.priorityClassName has been addressed
def get_cnv_pod_names_with_open_bugs():
    """
    For multiple pods currently we have missing spec.priorityClassName, this would cause the test validating existence
    of spec.priorityClassName for all cnv pods, to fail. To ensure test continues to run while those bugs are
    getting fixed, this workaround is being added. This utility function will be removed when all the associated bugs
    have been fixed

    Returns:
        list: names of pod types
    """
    pods_with_bugs = {
        "cdi-operator": 2008949,
        "hostpath-provisioner-operator": 2008949,
        "hyperconverged-cluster-cli-download": 2008938,
        "node-maintenance-operator": 2008960,
        "ssp-operator": 2008975,
        "virt-template-validator": 2008975,
    }
    return [
        pod_type
        for pod_type, bug_id in pods_with_bugs.items()
        if get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(),
            bug=bug_id,
        )
        not in BUG_STATUS_CLOSED
    ]


def validate_cnv_pods_priority_class_name_exists(cnv_pods):
    """
    Validates spec.priorityClassName is present for all cnv pods

    Args:
        cnv_pods(list): list of cnv pods

    Raises:
        AssertionError: if pods without spec.priorityClassName is found.
    """
    cnv_pod_names_with_open_bugs = get_cnv_pod_names_with_open_bugs()
    LOGGER.info(
        f"Following pods has associated bugzilla open: {cnv_pod_names_with_open_bugs}"
    )
    pods_no_priority_class = [
        pod.name
        for pod in cnv_pods
        if not pod.instance.spec.priorityClassName
        and not pod.name.startswith(tuple(cnv_pod_names_with_open_bugs))
    ]

    assert not pods_no_priority_class, (
        f"For the following cnv pods, spec.priorityClassName is missing "
        f"{pods_no_priority_class}"
    )


def validate_priority_class_value(cnv_pods):
    """
    Validates spec.priorityClassName contains valid values for all cnv pods

    Args:
        cnv_pods(list): list of cnv pods

    Raises:
        AssertionError: if pods with invalid values for spec.priorityClassName is found.
    """
    pods_invalid_priority_class = {
        pod.name: pod.instance.spec.priorityClassName
        for pod in cnv_pods
        if pod.instance.spec.priorityClassName
        and pod.instance.spec.priorityClassName not in VALID_PRIORITY_CLASS
    }
    assert not pods_invalid_priority_class, (
        f"For the following pods, unexpected priority class found"
        f": {pods_invalid_priority_class}"
    )
