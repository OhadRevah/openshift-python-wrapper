import re

from utilities.infra import ResourceMismatch, is_bug_open


def validate_liveness_probe_fields(deployment):
    """
    Validates that for a given deployment object values of certain "livenessProbe" fields matches with expected
    values

    Args:
        deployment (Deployment object): Deployment object to be used for field validation

    Raises:
        Asserts on mismatch between expected and actual values of livenessProbe fields
    """
    field_expected_values = {
        "initialDelaySeconds": 30,
        "periodSeconds": 5,
        "failureThreshold": 1,
    }

    containers_with_mismatches = {
        container["name"]: {
            field_name: {
                "expected": field_expected_values[field_name],
                "actual": container["livenessProbe"][field_name],
            }
            for field_name in field_expected_values
            if container["livenessProbe"][field_name]
            != field_expected_values[field_name]
        }
        for container in deployment.instance.spec.template.spec.containers
    }
    if any(containers_with_mismatches.values()):
        raise ResourceMismatch(
            f"For deployment: {deployment.name}, following livenessProbe fields failed "
            f"validations: {containers_with_mismatches}"
        )


def validate_request_fields(deployment, cpu_min_value):
    """
    Validates that for a given deployment object, for each containers: resources.requests contains cpu and memory
    fields. Cpu values can not be less than cpu_min_value

    Args:
        deployment (Deployment object): Deployment object to be used for field validation
        cpu_min_value (int): Minimum value of cpu resource request

    Raises:
        AssertionError: if resources.requests does not contains both cpu and memory, or if cpu request value is less
        than cpu_min_value
    """

    field_keys = ["cpu", "memory"]
    containers = deployment.instance.spec.template.spec.containers
    missing_cpu_memory_values = {
        container["name"]: [
            field_key
            for field_key in field_keys
            if not container["resources"]["requests"].get(field_key)
        ]
        for container in containers
    }
    assert not any(missing_cpu_memory_values.values()), (
        f"For deployment: {deployment.name}, following resources.requests fields are missing: "
        f"{missing_cpu_memory_values}"
    )

    cpu_values = {
        container["name"]: container["resources"]["requests"].get("cpu")
        for container in containers
    }
    cpu_value_pattern = re.compile(r"^\d+")

    invalid_cpus = {
        key: value
        for key, value in cpu_values.items()
        if int(cpu_value_pattern.findall(value)[0]) < cpu_min_value
    }
    if invalid_cpus:
        raise ResourceMismatch(
            f"For deployment {deployment.name} mismatch in cpu values found: {invalid_cpus}, "
            f"expected cpu values < {cpu_min_value}"
        )


def validate_cnv_deployments_priorty_class(cnv_deployments):
    deployments_with_bug = {"node-maintenance-operator": 2008960}
    cnv_deployment_names_with_open_bugs = [
        deployment
        for deployment, bug_id in deployments_with_bug.items()
        if is_bug_open(bug_id=bug_id)
    ]

    cnv_deployments_with_missing_priority_class = [
        deployment.name
        for deployment in cnv_deployments
        if not deployment.instance.spec.template.spec.priorityClassName
        and not deployment.name.startswith(tuple(cnv_deployment_names_with_open_bugs))
    ]

    assert not cnv_deployments_with_missing_priority_class, (
        "For the following cnv deployments, spec.template.spec.priorityClassName has not been set "
        f"{cnv_deployments_with_missing_priority_class}"
    )
