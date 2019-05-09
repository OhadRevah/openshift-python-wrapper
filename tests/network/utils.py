from utilities.utils import generate_yaml_from_template


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
