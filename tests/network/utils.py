import contextlib
import logging

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


class Bridge:
    def __init__(self, name, worker_pods):
        self.name = name
        self._worker_pods = worker_pods

    def __enter__(self):
        # use ExitStack to guarantee cleanup even when some nodes fail to
        # create the bridge
        with contextlib.ExitStack() as stack:
            for pod in self._worker_pods:
                # create the bridge on a particular node
                LOGGER.info(f"Adding bridge {self.name} using {pod.name}")
                pod.execute(
                    command=["ip", "link", "add", self.name, "type", "bridge"],
                    container=pod.containers()[0].name
                )

                # register a cleanup callback for the bridge just created
                def delete_bridge(pod):
                    LOGGER.info(f"Deleting bridge {self.name} using {pod.name}")
                    pod.execute(
                        command=["ip", "link", "del", self.name],
                        container=pod.containers()[0].name
                    )
                stack.callback(delete_bridge, pod)

            # all nodes now have the bridge, pass control to caller
            yield self

    def __exit__(self, *args):
        pass
