# -*- coding: utf-8 -*-

import pytest
from resources.service_account import ServiceAccount
from resources.utils import TimeoutSampler
from tests.compute.utils import WinRMcliPod


@pytest.fixture(scope="module")
def sa_ready(namespace):
    #  Wait for 'default' service account secrets to be exists.
    #  The Pod creating will fail if we try to create it before.
    default_sa = ServiceAccount(name="default", namespace=namespace.name)
    sampler = TimeoutSampler(
        timeout=10, sleep=1, func=lambda: default_sa.instance.secrets
    )
    for sample in sampler:
        if sample:
            return


@pytest.fixture(scope="module")
def winrmcli_pod(namespace, sa_ready, unprivileged_client):
    """
    Deploy winrm-cli Pod into the same namespace.
    """
    with WinRMcliPod(name="winrmcli-pod", namespace=namespace.name) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=60)
        yield pod
