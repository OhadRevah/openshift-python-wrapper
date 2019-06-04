import logging
import operator

from _pytest.fixtures import FixtureLookupError
from autologs.autologs import generate_logs

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


# TODO: break to small functions.
def create_vm_from_template(
    default_client, name, namespace, template, template_params,
    vm_params, bond_supported=None, is_bare_metal=None
):
    """
    Create VM from template (Jinja)

    template_params are the params that sent to the template.
    For example to set 512Mi memory send
    template_kwargs = {
        "memory": "512Mi"
        }

    To create a VM named vm-fedora-1 with cloud-init data and 4 interfaces with IPs send:
    vm_params = {
        "cloud_init": {
            "bootcmd": ["dnf install -y iperf3 qemu-guest-agent"],
            "runcmd": ["systemctl start qemu-guest-agent"]
            },
        "interfaces": {
            BRIDGE_BR1: ["192.168.0.1"],
            BRIDGE_BR1VLAN100: ["192.168.1.1"],
            BRIDGE_BR1VLAN200: ["192.168.2.1"],
            },
        "bonds": {
            BRIDGE_BR1BOND: ["192.168.3.1"],
            }
        }
    """
    nmcli_add_con = "nmcli con add type ethernet con-name"
    vm_object = VirtualMachine(name=name, namespace=namespace)
    boot_cmd = vm_params.get("cloud_init", {}).get("bootcmd")
    run_cmd = vm_params.get("cloud_init", {}).get("runcmd")
    template_params["name"] = name
    json_out = utils.generate_yaml_from_template(file_=template, **template_params)
    spec = json_out.get('spec').get('template').get('spec')
    vm_metadata = vm_params.get("metadata")
    if vm_metadata:
        json_out['spec']['template']['metadata'].update(vm_metadata)

    interfaces = spec.get('domain').get('devices').get('interfaces')
    networks = spec.get('networks')
    for interface in vm_params.get("interfaces", []):
        if interface == "pod":
            continue

        interfaces.append({'bridge': {}, 'name': interface})
        networks.append({'multus': {'networkName': interface}, 'name': interface})

    if bond_supported:
        for bond in vm_params.get("bonds", []):
            interfaces.append({'bridge': {}, 'name': bond})
            networks.append({'multus': {'networkName': bond}, 'name': bond})

    spec['domain']['devices']['interfaces'] = interfaces
    spec['networks'] = networks

    volumes = spec.get('volumes')
    cloud_init = [i for i in volumes if 'cloudInitNoCloud' in i][0]
    cloud_init_data = volumes.pop(volumes.index(cloud_init))
    cloud_init_user_data = cloud_init_data.get('cloudInitNoCloud').get('userData')
    if boot_cmd:
        cloud_init_user_data += "\nbootcmd:\n"
        for cmd in boot_cmd:
            cloud_init_user_data += f"  - {cmd}\n"

    if run_cmd:
        cloud_init_user_data += "\nruncmd:\n"
        for cmd in run_cmd:
            cloud_init_user_data += f"  - {cmd}\n"

    if cloud_init_user_data and "runcmd" not in cloud_init_user_data:
        cloud_init_user_data += "\nruncmd:\n"

    idx = 1
    all_interfaces = []
    for _, ips in vm_params.get("interfaces", {}).items():
        eth_name = f"eth{idx}"
        all_interfaces.append(eth_name)
        cloud_init_user_data += f"  - {nmcli_add_con} {eth_name} ifname {eth_name}\n"
        for ip in ips:
            cloud_init_user_data += f"  - nmcli con mod {eth_name} ipv4.addresses {ip}/24 ipv4.method manual\n"

        idx += 1

    if bond_supported:
        for _, ips in vm_params.get("bonds", {}).items():
            eth_name = f"eth{idx}"
            all_interfaces.append(eth_name)
            cloud_init_user_data += f"  - {nmcli_add_con} {eth_name} ifname {eth_name}\n"
            for ip in ips:
                cloud_init_user_data += f"  - nmcli con mod {eth_name} ipv4.addresses {ip}/24 ipv4.method manual\n"

            idx += 1

    if not is_bare_metal:
        for eth in all_interfaces:
            cloud_init_user_data += f"  - ip link set mtu 1450 {eth}\n"

    cloud_init_data['cloudInitNoCloud']['userData'] = cloud_init_user_data
    volumes.append(cloud_init_data)
    spec['volumes'] = volumes
    json_out['spec']['template']['spec'] = spec
    assert vm_object.create_from_dict(
        dyn_client=default_client, data=json_out, namespace=namespace
    )
    return vm_object


class FedoraVirtualMachine(VirtualMachine):
    def __init__(self, name, namespace, interfaces=None, networks=None, **vm_attr):
        super().__init__(name=name, namespace=namespace)
        self.interfaces = interfaces or []
        self.networks = networks or {}
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

        return res

    def set_cloud_init(self, res, user_data):
        volumes = res['spec']['template']['spec']['volumes']
        cloudinitdisk_data = [i for i in volumes if i['name'] == 'cloudinitdisk'][0]
        cloudinitdisk_idx = volumes.index(cloudinitdisk_data)
        volumes.pop(cloudinitdisk_idx)
        cloudinitdisk_data['cloudInitNoCloud']['userData'] = user_data
        volumes.append(cloudinitdisk_data)
        res['spec']['template']['spec']['volumes'] = volumes
        return res
