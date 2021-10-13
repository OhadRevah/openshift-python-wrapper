import logging
import re

from utilities.infra import BUG_STATUS_CLOSED, get_bug_status


VALID_PRIORITY_CLASS = [
    "openshift-user-critical",
    "system-cluster-critical",
    "system-node-critical",
    "kubevirt-cluster-critical",
]

LOGGER = logging.getLogger(__name__)


# TODO: remove this function when all the pod related bugs for missing spec.priorityClassName/resources.requests has
# been addressed
def get_cnv_pod_names_with_open_bugs(field_name):
    if field_name == "priorityClass":
        pods_with_bugs = {
            "hostpath-provisioner": 2028209,
            "hostpath-provisioner-csi": 2028209,
            "node-maintenance-operator-controller-manager": 2008960,
        }
    elif field_name == "resources":
        pods_with_bugs = {
            "hostpath-provisioner": 2015327,
        }
    else:
        raise AssertionError(f"Invalid field_name {field_name}")
    return [
        pod_type
        for pod_type, bug_id in pods_with_bugs.items()
        if get_bug_status(
            bug=bug_id,
        )
        not in BUG_STATUS_CLOSED
    ]


def validate_cnv_pods_priority_class_name_exists(cnv_pods):
    cnv_pod_names_with_open_bugs = get_cnv_pod_names_with_open_bugs(
        field_name="priorityClass"
    )
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


def validate_cnv_pod_resource_request(cnv_pod, request_field):
    containers = cnv_pod.instance.spec.containers

    missing_field_values = [
        container["name"]
        for container in containers
        if not container.get("resources", {}).get("requests", {}).get(request_field)
    ]
    return missing_field_values


def validate_cnv_pod_cpu_min_value(cnv_pod, cpu_min_value):
    containers = cnv_pod.instance.spec.containers
    cpu_values = {
        container["name"]: container.get("resources", {}).get("requests", {}).get("cpu")
        for container in containers
    }
    LOGGER.info(f"For {cnv_pod.name} cpu_values: {cpu_values}")
    cpu_value_pattern = re.compile(r"^\d+")
    # Get the pods for which resources.requests.cpu value does not meet minimum threshold requirement
    invalid_cpus = {
        key: value
        for key, value in cpu_values.items()
        if value and int(cpu_value_pattern.findall(value)[0]) < cpu_min_value
    }
    return invalid_cpus


def validate_cnv_pods_resource_request(cnv_pods, request_field):
    cnv_pod_names_with_open_bugs = get_cnv_pod_names_with_open_bugs(
        field_name="resources"
    )
    errors = {}
    for pod in cnv_pods:
        value = validate_cnv_pod_resource_request(
            cnv_pod=pod, request_field=request_field
        )
        if value:
            LOGGER.error(
                f"For {pod.name}, resources.requests.{request_field} is missing."
            )
            if not pod.name.startswith(tuple(cnv_pod_names_with_open_bugs)):
                LOGGER.info(f"For pod {pod.name}, missing {request_field}")
                errors[pod.name] = value

    assert (
        not errors
    ), f"For following pods resource.requests fields were missing: {errors}"
