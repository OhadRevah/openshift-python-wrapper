import json
import logging

import bitmath
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from utilities import console


LOGGER = logging.getLogger(__name__)


class BondNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        bond_name,
        nics,
        nodes,
        worker_pods,
        mode,
        node_selector=None,
        mtu=None,
        teardown=True,
        ipv4_dhcp=False,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            teardown=teardown,
            mtu=mtu,
            ipv4_dhcp=ipv4_dhcp,
        )
        self.bond_name = bond_name
        self.nodes = nodes
        self.nics = nics
        self.mode = mode

    def to_dict(self):
        if not self.iface:
            self.iface = {
                "name": self.bond_name,
                "type": "bond",
                "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
                "mtu": self.mtu,
                "link-aggregation": {
                    "mode": self.mode,
                    "slaves": self.nics,
                    "options": {"miimon": "120"},
                },
            }
            if self.mtu:
                for port in self.nics:
                    _port = {
                        "name": port,
                        "type": "ethernet",
                        "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
                        "mtu": self.mtu,
                    }
                    self.set_interface(_port)

        self.set_interface(self.iface)
        if self.iface not in self.ifaces:
            self.ifaces.append(self.iface)

        res = super().to_dict()
        return res


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
