# -*- coding: utf-8 -*-

from autologs.autologs import generate_logs

from resources.pod import Pod
from tests.network import config
from utilities import utils


@generate_logs()
def get_host_veth_sampler(pod, pod_container, expect_host_veth):
    """
    Wait until host veth are equal to expected veth number

    Args:
        pod (Pod): Pod object.
        pod_container (str): Pod container name.
        expect_host_veth (int): Expected number of veth on the host.

    Returns:
        bool: True if current veth number == expected veth number, False otherwise.
    """
    out = pod.exec(command=config.IP_LINK_SHOW_VETH_CMD, container=pod_container)[1]
    return int(out.strip()) == expect_host_veth


@generate_logs()
def wait_for_pods_to_match_compute_nodes_number(number_of_nodes):
    """
    Wait for pods to be created from DaemonSet

    Args:
        number_of_nodes (int): Number of nodes to match for.

    Returns:
        bool: True if Pods created.

    Raises:
        TimeoutExpiredError: After timeout reached.

    """
    sampler = utils.TimeoutSampler(
        timeout=30, sleep=1, func=Pod().list_names, label_selector="app=privileged-test-pod"
    )
    for sample in sampler:
        if len(sample) == number_of_nodes:
            return True
