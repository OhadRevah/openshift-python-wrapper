import logging

from openshift.dynamic.exceptions import ConflictError
from resources.utils import TimeoutSampler

from .resource import Resource


LOGGER = logging.getLogger(__name__)


class NodeNetworkConfigurationPolicy(Resource):

    api_group = "nmstate.io"

    class Interface:
        class State:
            UP = "up"
            DOWN = "down"
            ABSENT = "absent"

    def __init__(self, name, worker_pods=None, node_selector=None, teardown=True):
        super().__init__(name=name, teardown=teardown)
        self.desired_state = {"interfaces": []}
        self.node_selector = node_selector
        self.worker_pods = worker_pods
        if self.node_selector:
            for pod in self.worker_pods:
                if pod.node.name == self.node_selector:
                    self.worker_pods = [pod]
                    break

    def set_interface(self, interface):
        # First drop the interface if it's already in the list
        interfaces = [
            i
            for i in self.desired_state["interfaces"]
            if not (i["name"] == interface["name"])
        ]

        # Add the interface
        interfaces.append(interface)
        self.desired_state["interfaces"] = interfaces

    def to_dict(self):
        res = super()._base_body()
        res.update({"spec": {"desiredState": self.desired_state}})
        if self.node_selector:
            res["spec"]["nodeSelector"] = {"kubernetes.io/hostname": self.node_selector}

        return res

    def apply(self):
        resource = self.to_dict()
        samples = TimeoutSampler(
            timeout=3,
            sleep=1,
            exceptions=ConflictError,
            func=self.update,
            resource_dict=resource,
        )
        for _sample in samples:
            return
