import json

import bitmath

from utilities import console


def run_test_guest_performance(server_vm, client_vm, listen_ip):
    """
    In-guest performance bandwidth passthrough

    Args:
        server_vm (str): VM name that will be IPERF server
        client_vm (str): VM name that will be IPERF client
        listen_ip (str): The IP to listen on the server
    """
    with console.Fedora(vm=server_vm) as server_vm_console:
        server_vm_console.sendline(f"iperf3 -sB {listen_ip} &")
        with console.Fedora(vm=client_vm) as client_vm_console:
            client_vm_console.sendline(f"iperf3 -c {listen_ip} -t 5 -u -J")
            client_vm_console.expect("}\r\r\n}\r\r\n")
            iperf_data = client_vm_console.before

    iperf_data += "}\r\r\n}\r\r\n"
    iperf_json = json.loads(iperf_data[iperf_data.find("{") :])  # noqa: E203
    sum_sent = iperf_json.get("end").get("sum")
    bits_per_second = int(sum_sent.get("bits_per_second"))
    return float(bitmath.Byte(bits_per_second).GiB)
