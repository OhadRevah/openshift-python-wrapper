import logging
from collections import defaultdict

import pytest

from utilities.infra import get_node_audit_log_line_dict


LOGGER = logging.getLogger(__name__)

POD_SECURITY_LOG_ENTRY = "pod-security.kubernetes.io/audit-violations"


class PodSecurityViolationError(Exception):
    pass


@pytest.fixture()
def pod_security_violations_apis_calls(audit_logs, hco_namespace):
    failed_api_calls = defaultdict(list)
    for node, logs in audit_logs.items():
        for audit_log_entry_dict in get_node_audit_log_line_dict(
            logs=logs, node=node, log_entry=POD_SECURITY_LOG_ENTRY
        ):
            pod_security_annotations = audit_log_entry_dict["annotations"].get(
                POD_SECURITY_LOG_ENTRY
            )
            user_agent = audit_log_entry_dict["userAgent"]
            component_namespace = audit_log_entry_dict["objectRef"].get("namespace")
            if (
                pod_security_annotations
                and "would violate PodSecurity" in pod_security_annotations
                and component_namespace == hco_namespace.name
            ):
                failed_api_calls[user_agent].append(audit_log_entry_dict)
    return failed_api_calls


@pytest.mark.polarion("CNV-9115")
def test_cnv_pod_security_violation_audit_logs(pod_security_violations_apis_calls):
    LOGGER.info("Test pod security violations API calls:")
    if pod_security_violations_apis_calls:
        formatted_output = ""
        for user_agent, errors in pod_security_violations_apis_calls.items():
            formatted_output += f"User-agent: {user_agent}, Violations:\n"
            for error in errors:
                formatted_output += f"\t{error}\n"
            formatted_output += f"{'-' * 100}\n"
        raise PodSecurityViolationError(formatted_output)
