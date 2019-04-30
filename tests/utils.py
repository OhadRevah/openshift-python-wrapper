import json
import logging
import operator

import bitmath
from _pytest.fixtures import FixtureLookupError
from autologs.autologs import generate_logs

from utilities import utils, console
from . import config

LOGGER = logging.getLogger(__name__)


@generate_logs()
def wait_for_vm_interfaces(vmi, timeout=600):
    """
    Wait until guest agent report VMI network interfaces.

    Args:
        vmi (VirtualMachineInstance): VMI object.
        timeout (int): Maximum time to wait for interfaces status

    Returns:
        bool: True if agent report VMI interfaces.

    Raises:
        TimeoutExpiredError: After timeout reached.
    """
    sampler = utils.TimeoutSampler(timeout=timeout, sleep=1, func=vmi.get)
    LOGGER.info('Wait until guest agent is active')
    try:
        for sample in sampler:
            #  Check if guest agent is activate
            agent_status = [
                i for i in sample.get('status', {}).get('conditions', {}) if
                i.get('type') == 'AgentConnected' and i.get('status') == 'True'
            ]
            if agent_status:
                LOGGER.info('Wait until VMI report network interfaces status')
                for sample in sampler:
                    #  Get MVI interfaces from guest agent
                    ifcs = sample.get('status', {}).get('interfaces', [])
                    active_ifcs = [
                        i for i in ifcs if i.get('ipAddress') and i.get('interfaceName')
                    ]
                    if len(active_ifcs) == len(ifcs):
                        return True
                LOGGER.error('VMI did not report network interfaces status in given time')

    except utils.TimeoutExpiredError:
        LOGGER.error('Guest agent is not installed or not active')
        raise


def get_fixture_val(request, attr_name, default_value=None):
    """
    Get request.getfixturevalue()

    Args:
        request (Request): request fixture object
        attr_name (str): Attribute name to get
        default_value (any): Default value if attribute not found

    Returns:
        any: fixturevalue if found else default value
    """

    def get_attr_helper(attribute, obj, default=None):
        """
        Helper to get attribute value from any object, works with nested
        attributes like obj.attr1.attr2.attr3

        Args:
            attribute (str): path to the attribute
            obj (object): object to get attribute from
            default: default value is attribute is not found

        Returns:
            any: attr value if present, default otherwise
        """
        try:
            return operator.attrgetter(attribute)(obj)
        except AttributeError:
            return default

    try:
        val = request.getfixturevalue(attr_name)
        if val is None:
            raise FixtureLookupError(argname=attr_name, request=request)
        return val
    except FixtureLookupError:
        return get_attr_helper(attribute=attr_name, obj=request.cls, default=default_value)


def run_test_connectivity(src_vm, dst_vm, dst_ip, positive):
    """
    Check connectivity
    """
    expected = '0% packet loss' if positive else '100% packet loss'
    LOGGER.info(
        f"{'Positive' if positive else 'Negative'}: Ping {dst_ip} from {src_vm} to {dst_vm}"
    )
    with console.Fedora(vm=src_vm, namespace=config.NETWORK_NS) as src_vm_console:
        src_vm_console.sendline(f'ping -w 3 {dst_ip}')
        src_vm_console.expect(expected)


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
