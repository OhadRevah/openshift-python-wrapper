import contextlib
import logging

from pytest_testconfig import config as py_config

from resources.network_attachment_definition import BridgeNetworkAttachmentDefinition
from utilities.utils import generate_yaml_from_template

LOGGER = logging.getLogger(__name__)


def generate_network_cr_from_template(name, namespace, bridge=None, cni=None, vlan=None):
    """
    Generate network CR from template (Jinja)

    Args:
        name (str): Network name.
        namespace (str): Namespace where to create the network CR.
        bridge (str): Bridge name.
        cni (str): cni name. (cnv-bridge, bridge, ovs etc..)
        vlan (str): VLAN id.

    Returns:
        dict: Generated dict from the template.
    """
    file_ = "tests/manifests/network/network-cr-template.yml"
    template_params = {
        'name': name,
        'namespace': namespace,
        'bridge': bridge or name,
        'cni': cni or 'cnv-bridge',
        'vlan': f'"vlan": {vlan},' if vlan else ''
    }
    return generate_yaml_from_template(file_=file_, **template_params)


@contextlib.contextmanager
def _bridge(pod, name):
    LOGGER.info(f"Adding bridge {name} using {pod.name}")
    pod.execute(
        command=["ip", "link", "add", name, "type", "bridge"],
        container=pod.containers()[0].name
    )
    try:
        yield
    finally:
        LOGGER.info(f"Deleting bridge {name} using {pod.name}")
        pod.execute(
            command=["ip", "link", "del", name],
            container=pod.containers()[0].name
        )


class Bridge:
    def __init__(self, name, worker_pods):
        self.name = name
        self._worker_pods = worker_pods
        self._stack = None

    def __enter__(self):
        # use ExitStack to guarantee cleanup even when some workers fail
        with contextlib.ExitStack() as stack:
            for pod in self._worker_pods:
                stack.enter_context(_bridge(pod, self.name))
            self._stack = stack.pop_all()
        return self

    def __exit__(self, *args):
        if self._stack is not None:
            self._stack.__exit__(*args)


@contextlib.contextmanager
def bridge_nad(namespace, name, bridge, vlan=None):
    cni_type = py_config['template_defaults']['bridge_cni_name']
    with BridgeNetworkAttachmentDefinition(
            namespace=namespace.name,
            name=name,
            bridge_name=bridge,
            cni_type=cni_type,
            vlan=vlan) as nad:
        yield nad
