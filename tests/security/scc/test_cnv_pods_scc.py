# -*- coding: utf-8 -*-

"""
Tests to check, HCO Namespace Pod's, Security Context Constraint
"""

import logging

import pytest

from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)

POD_SCC_ALLOWLIST = [
    "restricted",
    "hostpath-provisioner",
    "containerized-data-importer",
    "bridge-marker",
    "linux-bridge",
    "nmstate",
    "ovs-cni-marker",
    "kubevirt-handler",
    "kubevirt-node-labeller",
]

# List of pods with anyuid SCC:
POD_SCC_ANYUID = ["vm-import-controller"]


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


@pytest.mark.polarion("CNV-4211")
def test_pods_scc_in_allowlist(skip_not_openshift, cnv_pods):
    """
    Validate that Pods in hco_namespace (openshift-cnv) have SCC from a predefined allowlist.
    """
    bugzilla = {
        "1834839": "cluster-network-addons-operator",
        "1930439": "hco-operator",
    }
    bugzilla = {
        bug_id: component
        for bug_id, component in bugzilla.items()
        if get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=bug_id
        )
        not in BUG_STATUS_CLOSED
    }
    failed_pods = []
    for pod in cnv_pods:
        LOGGER.info(f"Currently Validating {pod.name} Pod.")
        pod_bug_id = [
            bug_id for bug_id, pod_name in bugzilla.items() if pod_name in pod.name
        ]
        if pod_bug_id:
            LOGGER.info(f"Currently bug {pod_bug_id} for {pod.name}")
            continue
        pod_annotation = pod.instance.metadata.annotations.get("openshift.io/scc")
        if pod_annotation not in POD_SCC_ALLOWLIST and not (
            list(filter(pod.name.startswith, POD_SCC_ANYUID))
            and pod_annotation == "anyuid"
        ):
            failed_pods.append(pod.name)

    assert not failed_pods, f"Failed pods: {' '.join(failed_pods)}"
