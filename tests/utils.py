import logging
import operator
import urllib.error
import urllib.request

from _pytest.fixtures import FixtureLookupError
from autologs.autologs import generate_logs
from pytest_testconfig import config as py_config

from resources.virtual_machine import VirtualMachine
from utilities import utils

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
    sampler = utils.TimeoutSampler(timeout=timeout, sleep=1, func=lambda: vmi.instance)
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


def get_images_http_server():
    """
    Fetch http_server url from config and return if available.
    """
    region = py_config['region']
    server = py_config[region]['http_server']
    try:
        assert urllib.request.urlopen(server).getcode() == 200
    except urllib.error.URLError:
        LOGGER.error('URL Error when testing connectivity to HTTP server')
        raise

    return server


class FedoraVirtualMachine(VirtualMachine):
    def __init__(
        self, name, namespace, interfaces=None, networks=None, cloud_init_user_data=None, **vm_attr
    ):
        super().__init__(name=name, namespace=namespace)
        self.interfaces = interfaces or []
        self.networks = networks or {}
        self.cloud_init_user_data = cloud_init_user_data
        self.vm_attrs = vm_attr
        self.vm_attrs_to_use = self.vm_attrs or {
                "label": "fedora-vm",
                "cpu_cores": 1,
                "memory": "1024Mi",
            }

    def _to_dict(self):
        res = super()._to_dict()
        json_out = utils.generate_yaml_from_template(
            file_="tests/manifests/vm-fedora.yaml",
            name=self.name,
            **self.vm_attrs_to_use)

        res['metadata'] = json_out['metadata']
        res['spec'] = json_out['spec']

        for iface_name in self.interfaces:
            res['spec']['template']["spec"]["domain"]["devices"]["interfaces"].append({
                "name": iface_name,
                "bridge": {},
            })

        for iface_name, network in self.networks.items():
            res['spec']['template']["spec"]["networks"].append({
                "name": iface_name,
                "multus": {
                    "networkName": network,
                },
            })

        if self.cloud_init_user_data:
            for vol in res['spec']['template']['spec']['volumes']:
                if vol['name'] == 'cloudinitdisk':
                    vol['cloudInitNoCloud']['userData'] = self.cloud_init_user_data
                    break

        return res
