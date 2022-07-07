import json
import logging
import subprocess
from collections import defaultdict

import pytest
from packaging.version import Version

from utilities.infra import is_bug_open


LOGGER = logging.getLogger(__name__)
OC_ADM_LOGS_COMMAND = "oc adm node-logs"
AUDIT_LOGS_PATH = "--path=kube-apiserver"
DEPRECATED_API_MAX_VERSION = "1.25"


class DeprecatedAPIError(Exception):
    """
    Raises when calling a deprecated API
    """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def get_deprecated_calls_from_log(log, node):
    return subprocess.getoutput(
        f'{OC_ADM_LOGS_COMMAND} {node} {AUDIT_LOGS_PATH}/{log} | grep \'"k8s.io/deprecated":"true"\''
    ).splitlines()


def get_deprecated_log_line_dict(logs, node):
    for log in logs:
        deprecated_api_lines = get_deprecated_calls_from_log(log=log, node=node)
        if deprecated_api_lines:
            for line in deprecated_api_lines:
                try:
                    yield json.loads(line)
                except json.decoder.JSONDecodeError:
                    LOGGER.error(f"Unable to parse line: {line!r}")
                    raise


def skip_component_check(user_agent, deprecation_version):
    ignored_components_list = [
        "cluster-version-operator",
        "kube-controller-manager",
        "cluster-policy-controller",
        "jaeger-operator",
        "rook",
    ]

    # Skip if deprecated version does not exist
    if not deprecation_version:
        return True

    # Skip OCP core and kubernetes components
    for comp_name in ignored_components_list:
        if comp_name in user_agent:
            return True

    # Skip if deprecated version is greater than DEPRECATED_API_MAX_VERSION
    if Version(deprecation_version) > Version(DEPRECATED_API_MAX_VERSION):
        return True

    return False


def failure_not_in_component_list(component, annotations, audit_log_entry_dict):
    object_ref_str = "objectRef"

    for failure_entry in component:
        if (
            annotations != failure_entry["annotations"]
            and audit_log_entry_dict[object_ref_str] != failure_entry[object_ref_str]
        ):
            return True

    return False


def format_printed_deprecations_dict(deprecated_calls):
    formatted_output = ""
    for comp, errors in deprecated_calls.items():
        formatted_output += f"Component: {comp}\n\nCalls:\n"
        for error in errors:
            formatted_output += f"\t{error}\n"
        formatted_output += "\n\n\n"

    return formatted_output


@pytest.fixture()
def audit_logs():
    """Get audit logs names"""
    output = subprocess.getoutput(
        f"{OC_ADM_LOGS_COMMAND} --role=master {AUDIT_LOGS_PATH} | grep audit"
    ).splitlines()
    nodes_logs = defaultdict(list)
    for data in output:
        try:
            node, log = data.split()
            nodes_logs[node].append(log)
        # When failing to get node log, for example "error trying to reach service: ... : connect: connection refused"
        except ValueError:
            LOGGER.error(f"Fail to get log: {data}")

    return nodes_logs


@pytest.fixture()
def deprecated_apis_calls(audit_logs):
    """Go over master nodes audit logs and look for calls using deprecated APIs"""
    failed_api_calls = defaultdict(list)
    for node, logs in audit_logs.items():
        for audit_log_entry_dict in get_deprecated_log_line_dict(logs=logs, node=node):
            annotations = audit_log_entry_dict["annotations"]
            user_agent = audit_log_entry_dict["userAgent"]
            component = failed_api_calls.get(user_agent)

            if skip_component_check(
                user_agent=user_agent,
                deprecation_version=annotations.get("k8s.io/removed-release"),
            ):
                continue

            # Add new component to dict if not already in it
            if not component:
                failed_api_calls[user_agent].append(audit_log_entry_dict)

            # Add failure dict if failure annotations and object_ref not in component list of errors
            else:
                if failure_not_in_component_list(
                    component=component,
                    annotations=annotations,
                    audit_log_entry_dict=audit_log_entry_dict,
                ):
                    failed_api_calls[user_agent].append(audit_log_entry_dict)

    return failed_api_calls


@pytest.fixture()
def filtered_deprecated_api_calls(deprecated_apis_calls):
    # Remove components with open bugs, key: component name (userAgent), value: bug id
    components_bugs = {
        "rook": 2079919,
    }
    for component in deprecated_apis_calls.copy():
        for comp, bug in components_bugs.items():
            if comp in component and is_bug_open(bug_id=bug):
                del deprecated_apis_calls[component]
                break

    return deprecated_apis_calls


@pytest.mark.polarion("CNV-6679")
def test_deprecated_apis_in_audit_logs(filtered_deprecated_api_calls):
    LOGGER.info(
        f"Test deprecated API calls, max version for deprecation check: {DEPRECATED_API_MAX_VERSION}"
    )
    if filtered_deprecated_api_calls:
        raise DeprecatedAPIError(
            message=format_printed_deprecations_dict(
                deprecated_calls=filtered_deprecated_api_calls
            )
        )
