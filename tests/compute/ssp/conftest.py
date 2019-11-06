# -*- coding: utf-8 -*-

import re
from contextlib import contextmanager

import pytest
from resources.service_account import ServiceAccount
from resources.template import Template
from resources.utils import TimeoutSampler
from tests.compute.utils import WinRMcliPod
from utilities.infra import get_images_external_http_server
from utilities.storage import DataVolumeTestResource
from utilities.virt import VirtualMachineForTestsFromTemplate, wait_for_vm_interfaces


"""
General tests fixtures
"""


@contextmanager
def data_volume(request, namespace):
    """ DV creation.

    The call to this function is triggered by calling either
    data_volume_scope_function or data_volume_scope_module.


    Example:
        @pytest.mark.parametrize('data_volume',
                                 [pytest.param(
                                {
                                "image": "rhel-images/rhel-76/rhel-76.qcow2",
                                "os_release": "7.6",
                                "template_labels": [
                                    f"{Template.Labels.OS}/rhel7.0",
                                    f"{Template.Labels.WORKLOAD}/server",
                                    f"{Template.Labels.FLAVOR}/tiny",
                                    ],
                                },
                                marks=(pytest.mark.polarion("CNV-2174")),
                                ),
                                ], indirect=True)
    """

    os = re.search(
        r"(\w+)/([a-zA-Z]*)",
        [i for i in request.param["template_labels"] if Template.Labels.OS in i][0],
    ).group(2)

    # Set dv attributes
    dv_kwargs = {
        "name": f"dv-{os}-{request.param['os_release'].replace(' ', '-')}".lower(),
        "namespace": namespace.name,
        "url": f"{get_images_external_http_server()}{request.param['image']}",
        "os_release": request.param["os_release"],
        "template_labels": request.param.get("template_labels", None),
        "size": request.param.get("dv_size", None),
        "access_modes": request.param.get("access_modes", None),
        "volume_mode": request.param.get("volume_mode", None),
        "storage_class": request.param.get("storage_class", None),
    }

    # Create dv
    with DataVolumeTestResource(
        **{k: v for k, v in dv_kwargs.items() if v is not None}
    ) as dv:
        dv.wait(timeout=1200 if "win" in os else 900)
        yield dv


@pytest.fixture()
def data_volume_scope_function(request, namespace):
    with data_volume(request, namespace) as dv:
        yield dv


@pytest.fixture(scope="module")
def data_volume_scope_module(request, namespace):
    with data_volume(request, namespace) as dv:
        yield dv


@contextmanager
def vm_from_template(request, unprivileged_client, namespace, data_volume):
    """ Create a VM from template and start it (if explicitly requested in
    request.param['start_vm'].

    The call to this function is triggered by calling either
    vm_from_template_scope_function or vm_from_template_scope_module.

    Prerequisite - a DV must be created prior to VM creation.
    """

    vm_name = f"{data_volume.name.strip('dv-')}"
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        labels=data_volume.template_labels,
        template_dv=data_volume.name,
    ) as vm:
        if hasattr(request, "param") and request.param.get("start_vm"):
            vm.start(wait=True)
            vm.vmi.wait_until_running()
            if request.param.get("guest_agent", True):
                wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm


@pytest.fixture()
def vm_from_template_scope_function(
    request, unprivileged_client, namespace, data_volume_scope_function
):
    with vm_from_template(
        request, unprivileged_client, namespace, data_volume_scope_function
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_from_template_scope_module(
    request, unprivileged_client, namespace, data_volume_scope_module
):
    with vm_from_template(
        unprivileged_client, namespace, data_volume_scope_module
    ) as vm:
        yield vm


"""
Windows-specific fixtures
"""


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
def winrmcli_pod(namespace, sa_ready):
    """
    Deploy winrm-cli Pod into the same namespace.
    """
    with WinRMcliPod(name="winrmcli-pod", namespace=namespace.name) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=60)
        yield pod
