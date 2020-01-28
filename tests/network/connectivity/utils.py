import json
import logging

import bitmath
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.pod import ExecOnPodError
from resources.utils import TimeoutExpiredError
from utilities import console
from utilities.network import set_iface_mtu


LOGGER = logging.getLogger(__name__)


class BondNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self, name, bond_name, nics, nodes, worker_pods, node_selector=None, mtu=None
    ):
        super().__init__(
            name=name, worker_pods=worker_pods, node_selector=node_selector
        )
        self.bond_name = bond_name
        self.nodes = nodes
        self.nics = nics
        self.bond = None
        self.mtu = mtu
        self.mtu_dict = {}

    def to_dict(self):
        if not self.bond:
            self.bond = {
                "name": self.bond_name,
                "type": "bond",
                "state": "up",
                "mtu": self.mtu,
                "link-aggregation": {
                    "mode": "active-backup",
                    "slaves": self.nics,
                    "options": {"miimon": "120"},
                },
            }

        self.set_interface(self.bond)
        res = super().to_dict()
        return res

    def __enter__(self):
        if self.mtu:
            for pod in self.worker_pods:
                for nic in self.nics:
                    self.mtu_dict[f"{pod.node.name}{nic}"] = pod.execute(
                        command=["cat", f"/sys/class/net/{nic}/mtu"]
                    ).strip()
                    set_iface_mtu(pod=pod, port=nic, mtu=self.mtu)

        super().__enter__()
        for node in self.nodes:
            try:
                node_network_state = NodeNetworkState(name=node)
                node_network_state.wait_until_up(self.bond_name)
            except TimeoutExpiredError:
                self.clean_up()
                raise
        return self

    def clean_up(self):
        self._absent_interface()
        self.wait_for_bond_deleted()
        self.delete()

    def __exit__(self, exception_type, exception_value, traceback):
        self.clean_up()
        if self.mtu:
            for pod in self.worker_pods:
                # Restore MTU
                for nic in self.nics:
                    mtu = self.mtu_dict[f"{pod.node.name}{nic}"]
                    try:
                        set_iface_mtu(pod=pod, port=nic, mtu=self.mtu)
                    except ExecOnPodError:
                        LOGGER.error(
                            f"Failed to restore MTU to {mtu} on {pod.node.name}"
                        )

    def _absent_interface(self):
        self.bond["state"] = "absent"
        self.set_interface(self.bond)
        self.apply()

    def wait_for_bond_deleted(self):
        for node in self.nodes:
            node_network_state = NodeNetworkState(name=node)
            node_network_state.wait_until_deleted(self.bond_name)


def run_test_guest_performance(server_vm, client_vm, listen_ip):
    """
    In-guest performance bandwidth passthrough

    Args:
        server_vm (str): VM name that will be IPERF server
        client_vm (str): VM name that will be IPERF client
        listen_ip (str): The IP to listen on the server
    """
    with console.Fedora(vm=server_vm) as server_vm_console:
        server_vm_console.sendline(f"iperf3 -sB {listen_ip}")
        with console.Fedora(vm=client_vm) as client_vm_console:
            client_vm_console.sendline(f"iperf3 -c {listen_ip} -t 5 -u -J")
            client_vm_console.expect("}\r\r\n}\r\r\n")
            iperf_data = client_vm_console.before
        server_vm_console.sendline(chr(3))  # Send ctrl+c to kill iperf3 server

    iperf_data += "}\r\r\n}\r\r\n"
    iperf_json = json.loads(iperf_data[iperf_data.find("{") :])  # noqa: E203
    sum_sent = iperf_json.get("end").get("sum")
    bits_per_second = int(sum_sent.get("bits_per_second"))
    return float(bitmath.Byte(bits_per_second).GiB)
