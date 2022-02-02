# -*- coding: utf-8 -*-

"""
Tests to check, HCO Namespace Pod's, Security Context Constraint
"""

import logging

import pytest

from utilities.constants import (
    BRIDGE_MARKER,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    LINUX_BRIDGE,
    SSP_OPERATOR,
)
from utilities.infra import is_bug_open


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


LOGGER = logging.getLogger(__name__)

POD_SCC_ALLOWLIST = [
    "restricted",
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    "containerized-data-importer",
    BRIDGE_MARKER,
    LINUX_BRIDGE,
    "nmstate",
    "ovs-cni-marker",
    "kubevirt-handler",
    "kubevirt-node-labeller",
]

# Tuple of pod prefixes with anyuid SCC annotation
POD_SCC_ANYUID = ("vm-import-controller",)


@pytest.mark.polarion("CNV-4438")
def test_openshiftio_scc_exists_bz1847594(skip_not_openshift, cnv_pods):
    """
    Validate that Pods in hco_namespace (openshift-cnv) have openshift.io/scc
    """
    failed_pods = []
    for pod in cnv_pods:
        if not pod.instance.metadata.annotations.get("openshift.io/scc"):
            failed_pods.append(pod.name)
    assert (
        not failed_pods
    ), f"The following pods do not have scc annotation: {failed_pods}"


@pytest.fixture()
def components_with_non_closed_bugs():
    bugzilla_component_name_dict = {
        "1834839": CLUSTER_NETWORK_ADDONS_OPERATOR,
        "1995295": SSP_OPERATOR,
    }
    return tuple(
        component_name
        for bug_id, component_name in bugzilla_component_name_dict.items()
        if is_bug_open(
            bug_id=bug_id,
        )
    )


@pytest.fixture()
def pods_not_whitelisted_or_anyuid(cnv_pods, components_with_non_closed_bugs):
    pods_scc_annotations_dict = {
        pod.name: pod.instance.metadata.annotations.get("openshift.io/scc")
        for pod in cnv_pods
        if not pod.name.startswith(components_with_non_closed_bugs)
    }
    return [
        pod_name
        for pod_name, pod_scc_annotation in pods_scc_annotations_dict.items()
        if not (pod_scc_annotation == "anyuid" and pod_name.startswith(POD_SCC_ANYUID))
        and pod_scc_annotation not in POD_SCC_ALLOWLIST
    ]


@pytest.mark.polarion("CNV-4211")
def test_pods_scc_in_allowlist(skip_not_openshift, pods_not_whitelisted_or_anyuid):
    """
    Validate that Pods in hco_namespace (openshift-cnv) have SCC from a predefined allowlist
    """
    assert (
        not pods_not_whitelisted_or_anyuid
    ), f"Pods not conforming to SCC annotation conditions: pods={pods_not_whitelisted_or_anyuid}"
