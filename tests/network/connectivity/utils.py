import json
import logging

import bitmath

from utilities import console
from . import config

LOGGER = logging.getLogger(__name__)


def run_test_connectivity(src_vm, dst_vm, dst_ip, positive):
    """
    Check connectivity
    """
    LOGGER.info(f"{'Positive' if positive else 'Negative'}: Ping {dst_ip} from {src_vm} to {dst_vm}")
    with console.Fedora(vm=src_vm, namespace=config.NETWORK_NS) as src_vm_console:
        src_vm_console.sendline(f'ping -w 3 {dst_ip}')
        src_vm_console.sendline('echo $?')
        src_vm_console.expect('0' if positive else '1')


def run_test_guest_performance(server_vm, client_vm, listen_ip):
    """
    In-guest performance bandwidth passthrough

    Args:
        server_vm (str): VM name that will be IPERF server
        client_vm (str): VM name that will be IPERF client
        listen_ip (str): The IP to listen on the server
    """
    namespace = config.NETWORK_NS
    with console.Fedora(vm=server_vm, namespace=namespace) as server_vm_console:
        server_vm_console.sendline(f'iperf3 -sB {listen_ip}')
        with console.Fedora(vm=client_vm, namespace=namespace) as client_vm_console:
            client_vm_console.sendline(f'iperf3 -c {listen_ip} -t 5 -u -J')
            client_vm_console.expect('}\r\r\n}\r\r\n')
            iperf_data = client_vm_console.before
        server_vm_console.sendline(chr(3))  # Send ctrl+c to kill iperf3 server

    iperf_data += '}\r\r\n}\r\r\n'
    iperf_json = json.loads(iperf_data[iperf_data.find('{'):])
    sum_sent = iperf_json.get('end').get('sum')
    bits_per_second = int(sum_sent.get('bits_per_second'))
    return float(bitmath.Byte(bits_per_second).GiB)
