import logging
import re
import subprocess
from collections import defaultdict

import pytest

from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)


LOGGER = logging.getLogger(__name__)
OC_ADM_LOGS_COMMAND = "oc adm node-logs"
ROLE_COMMAND = "--role=master"
AUDIT_LOGS_PATH = "--path=kube-apiserver"
DEPRECATED_API_VERSION = "1.22"
IGNORED_COMPONENTS_LIST = [
    "cluster-version-operator",
    "kube-controller-manager",
    "cluster-policy-controller",
]


@pytest.fixture()
def audit_logs():
    """Get audit logs names"""
    output = subprocess.getoutput(
        f"{OC_ADM_LOGS_COMMAND} {ROLE_COMMAND} {AUDIT_LOGS_PATH}| grep audit"
    ).splitlines()
    nodes_logs = defaultdict(list)
    for data in output:
        node, log = data.split()
        nodes_logs[node].append(log)

    return nodes_logs


def get_deprecated_apis(audit_logs_dict):
    """Go over master nodes audit logs and look for calls using deprecated APIs"""

    def _get_deprecated_calls_from_log(log):
        return subprocess.getoutput(
            f'{OC_ADM_LOGS_COMMAND} {node} {AUDIT_LOGS_PATH}/{log} | grep \'"k8s.io/deprecated":"true"\'|grep'
            f' \'"k8s.io/removed-release":"{DEPRECATED_API_VERSION}"\''
        ).splitlines()

    def _extract_data_from_log(line):
        return re.search(
            r'.*"userAgent":(?P<useragent>.*?),.'
            r'*"annotations".*(?P<reason>"authorization.k8s.io/reason":.*?),.*',
            line,
        ).groupdict()

    failed_api_calls = defaultdict(list)
    for node, logs in audit_logs_dict.items():
        for log in logs:
            output = _get_deprecated_calls_from_log(log=log)
            if output:
                for line in output:
                    result_dict = _extract_data_from_log(line=line)
                    user_agent = result_dict["useragent"]
                    component = failed_api_calls.get(user_agent)
                    # Add to dictionary only if the reason does not already exist or add a key for a new component
                    # Skip OCP core and kubernetes components
                    skip_component_check = [
                        True
                        for comp_name in IGNORED_COMPONENTS_LIST
                        if comp_name in user_agent
                    ]
                    if not skip_component_check and (
                        (
                            component
                            and [
                                True
                                for entry in component
                                if result_dict["reason"] not in entry
                            ]
                        )
                        or not component
                    ):
                        failed_api_calls[user_agent].append(line)

    return failed_api_calls


@pytest.mark.polarion("CNV-6679")
def test_deprecated_apis_in_audit_logs(audit_logs):
    LOGGER.info(f"Test deprecated API calls, version {DEPRECATED_API_VERSION}")
    deprecated_calls = get_deprecated_apis(audit_logs_dict=audit_logs)

    # Remove components with open bugs
    components_bugs = {"virt-api": 1972762, "node-maintenance-operator": 1972784}
    for component in deprecated_calls.copy():
        if [
            True
            for comp, bug in components_bugs.items()
            if comp in component
            and get_bug_status(
                bugzilla_connection_params=get_bugzilla_connection_params(), bug=bug
            )
            not in BUG_STATUS_CLOSED
        ]:
            deprecated_calls.pop(component)

    assert (
        not deprecated_calls
    ), f"The following APIs calls are deprecated: {deprecated_calls}"