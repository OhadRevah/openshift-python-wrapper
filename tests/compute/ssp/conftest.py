# -*- coding: utf-8 -*-

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.service_account import ServiceAccount
from resources.template import Template
from resources.utils import TimeoutSampler
from tests.compute.utils import WinRMcliPod
from utilities.infra import get_images_external_http_server
from utilities.storage import DataVolume, create_dv
from utilities.virt import VirtualMachineForTestsFromTemplate, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


"""
General tests fixtures
"""


def data_volume(request, namespace):
    """ DV creation.

    The call to this function is triggered by calling either
    data_volume_scope_function or data_volume_scope_class.
    """

    # Set dv attributes
    dv_kwargs = {
        "dv_name": request.param["dv_name"].replace(".", "-").lower(),
        "namespace": namespace.name,
        "source": "http",
        "url": f"{get_images_external_http_server()}{request.param['image']}",
        "size": request.param.get(
            "dv_size", "35Gi" if "win" in request.param["dv_name"] else "25Gi"
        ),
        "access_modes": request.param.get("access_modes", DataVolume.AccessMode.RWX),
        "volume_mode": request.param.get(
            "volume_mode", py_config["default_volume_mode"],
        ),
        "storage_class": request.param.get(
            "storage_class", py_config["default_storage_class"]
        ),
        "content_type": DataVolume.ContentType.KUBEVIRT,
    }

    # Create dv
    with create_dv(**{k: v for k, v in dv_kwargs.items() if v is not None}) as dv:
        dv.wait(timeout=1800 if "win" in request.param["dv_name"] else 1200)
        yield dv


@pytest.fixture()
def data_volume_scope_function(request, namespace):
    yield from data_volume(request, namespace)


@pytest.fixture(scope="class")
def data_volume_scope_class(request, namespace):
    yield from data_volume(request, namespace)


def vm_instance_from_template(request, unprivileged_client, namespace, data_volume):
    """ Create a VM from template and start it (if explicitly requested in
    request.param['start_vm'].

    The call to this function is triggered by calling either
    vm_instance_from_template_scope_function or vm_instance_from_template_scope_class.

    Prerequisite - a DV must be created prior to VM creation.
    """

    with VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"].replace(".", "-").lower(),
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**request.param["template_labels"]),
        template_dv=data_volume.name,
        vm_dict=request.param.get("vm_dict"),
        cpu_threads=request.param.get("cpu_threads"),
    ) as vm:
        if request.param.get("start_vm", True):
            vm.start(wait=True)
            vm.vmi.wait_until_running()
            if request.param.get("guest_agent", True):
                wait_for_vm_interfaces(vm.vmi)
        yield vm


@pytest.fixture()
def vm_instance_from_template_scope_function(
    request, unprivileged_client, namespace, data_volume_scope_function
):
    """ Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    yield from vm_instance_from_template(
        request, unprivileged_client, namespace, data_volume_scope_function
    )


@pytest.fixture(scope="class")
def vm_instance_from_template_scope_class(
    request, unprivileged_client, namespace, data_volume_scope_class
):
    """ Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    yield from vm_instance_from_template(
        request, unprivileged_client, namespace, data_volume_scope_function
    )


def vm_object_from_template(
    request, unprivileged_client, namespace, data_volume_scope_class
):
    """ Instantiate a VM object

    The call to this function is triggered by calling either
    vm_object_from_template_scope_function or vm_object_from_template_scope_class.
    """

    return VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"].replace(".", "-").lower(),
        namespace=namespace.name,
        client=unprivileged_client,
        template_dv=data_volume_scope_class.name,
        labels=Template.generate_template_labels(**request.param["template_labels"]),
        vm_dict=request.param.get("vm_dict"),
        cpu_threads=request.param.get("cpu_threads"),
    )


@pytest.fixture()
def vm_object_from_template_scope_function(
    request, unprivileged_client, namespace, data_volume_scope_function
):
    return vm_object_from_template(
        request, unprivileged_client, namespace, data_volume_scope_function
    )


@pytest.fixture(scope="class")
def vm_object_from_template_scope_class(
    request, unprivileged_client, namespace, data_volume_scope_class
):
    return vm_object_from_template(
        request, unprivileged_client, namespace, data_volume_scope_class
    )


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


def winrmcli_pod(namespace, sa_ready):
    """ Deploy winrm-cli Pod into the same namespace.

    The call to this function is triggered by calling either
    winrmcli_pod_scope_module or winrmcli_pod_scope_class.
    """

    with WinRMcliPod(name="winrmcli-pod", namespace=namespace.name) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=90)
        yield pod


@pytest.fixture()
def winrmcli_pod_scope_function(namespace, sa_ready):
    yield from winrmcli_pod(namespace, sa_ready)


@pytest.fixture(scope="module")
def winrmcli_pod_scope_module(namespace, sa_ready):
    yield from winrmcli_pod(namespace, sa_ready)


@pytest.fixture(scope="class")
def winrmcli_pod_scope_class(namespace, sa_ready):
    yield from winrmcli_pod(namespace, sa_ready)
