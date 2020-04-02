import logging

from openshift.dynamic.exceptions import ConflictError
from resources.utils import TimeoutExpiredError, TimeoutSampler

from .node_network_state import NodeNetworkState
from .resource import Resource


LOGGER = logging.getLogger(__name__)


class NodeNetworkConfigurationPolicy(Resource):

    api_group = "nmstate.io"

    class Interface:
        class State:
            UP = "up"
            DOWN = "down"
            ABSENT = "absent"

    def __init__(
        self,
        name,
        worker_pods=None,
        node_selector=None,
        teardown=True,
        mtu=None,
        ports=None,
        ipv4_dhcp=None,
    ):
        super().__init__(name=name, teardown=teardown)
        self.desired_state = {"interfaces": []}
        self.worker_pods = worker_pods
        self.mtu = mtu
        self.mtu_dict = {}
        self.ports = ports or []
        self.iface = None
        self.ifaces = []
        self._ipv4_dhcp = ipv4_dhcp
        self.ipv4_iface_state = {}
        self.node_selector = node_selector
        if self.node_selector:
            for pod in self.worker_pods:
                if pod.node.name == node_selector:
                    self.worker_pods = [pod]
                    self._node_selector = {"kubernetes.io/hostname": self.node_selector}
                    break
        else:
            self._node_selector = {"node-role.kubernetes.io/worker": ""}

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
        if self._node_selector:
            res["spec"]["nodeSelector"] = self._node_selector

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

    def __enter__(self):
        if self._ipv4_dhcp:
            self._ipv4_state_backup()

        if self.mtu:
            for pod in self.worker_pods:
                for port in self.ports:
                    self.mtu_dict[port] = pod.execute(
                        command=["cat", f"/sys/class/net/{port}/mtu"]
                    ).strip()

        super().__enter__()

        try:
            self.validate_create()
            return self
        except Exception as e:
            LOGGER.error(e)
            self.clean_up()
            raise

    def __exit__(self, exception_type, exception_value, traceback):
        if not self.teardown:
            return
        self.clean_up()

    @property
    def ipv4_dhcp(self):
        return self._ipv4_dhcp

    @ipv4_dhcp.setter
    def ipv4_dhcp(self, ipv4_dhcp):
        if ipv4_dhcp != self._ipv4_dhcp:
            self._ipv4_dhcp = ipv4_dhcp

            if self._ipv4_dhcp:
                self._ipv4_state_backup()
                self.iface["ipv4"] = {"dhcp": True, "enabled": True}

            self.set_interface(self.iface)
            self.apply()

    def clean_up(self):
        if self.mtu:
            for port in self.ports:
                _port = {
                    "name": port,
                    "type": "ethernet",
                    "state": self.Interface.State.UP,
                    "mtu": int(self.mtu_dict[port]),
                }
                self.set_interface(_port)
                self.apply()
        try:
            self._absent_interface()
            self.wait_for_bridge_deleted()
        except TimeoutExpiredError as e:
            LOGGER.error(e)

        self.delete()

    def wait_for_bridge_deleted(self):
        for pod in self.worker_pods:
            for bridge in self.ifaces:
                node_network_state = NodeNetworkState(name=pod.node.name)
                node_network_state.wait_until_deleted(bridge["name"])

    def validate_create(self):
        for pod in self.worker_pods:
            for bridge in self.ifaces:
                node_network_state = NodeNetworkState(name=pod.node.name)
                node_network_state.wait_until_up(bridge["name"])

    def _ipv4_state_backup(self):
        # Backup current state of dhcp for the interfaces which arent veth or current bridge
        for pod in self.worker_pods:
            node_network_state = NodeNetworkState(name=pod.node.name)
            self.ipv4_iface_state[pod.node.name] = {}
            for interface in node_network_state.instance.status.currentState.interfaces:
                if interface["name"] in self.ports:
                    self.ipv4_iface_state[pod.node.name].update(
                        {
                            interface["name"]: {
                                k: interface["ipv4"][k] for k in ("dhcp", "enabled")
                            }
                        }
                    )

    def _absent_interface(self):
        for bridge in self.ifaces:
            bridge["state"] = self.Interface.State.ABSENT
            self.set_interface(bridge)

            if self._ipv4_dhcp:
                temp_ipv4_iface_state = {}
                for pod in self.worker_pods:
                    node_network_state = NodeNetworkState(name=pod.node.name)
                    temp_ipv4_iface_state[pod.node.name] = {}
                    # Find which interfaces got changed (of those that are connected to bridge)
                    for (
                        interface
                    ) in node_network_state.instance.status.currentState.interfaces:
                        if interface["name"] in self.ports:
                            x = {k: interface["ipv4"][k] for k in ("dhcp", "enabled")}
                            if (
                                self.ipv4_iface_state[pod.node.name][interface["name"]]
                                != x
                            ):
                                temp_ipv4_iface_state[pod.node.name].update(
                                    {
                                        interface["name"]: self.ipv4_iface_state[
                                            pod.node.name
                                        ][interface["name"]]
                                    }
                                )

                previous_state = next(iter(temp_ipv4_iface_state.values()))

                # Restore DHCP state of the changed bridge connected ports
                for iface_name, ipv4 in previous_state.items():
                    interface = {"name": iface_name, "ipv4": ipv4}
                    self.set_interface(interface)

        self.apply()
