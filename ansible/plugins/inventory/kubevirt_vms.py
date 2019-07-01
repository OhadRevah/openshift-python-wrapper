#!/usr/bin/env python
# vim: sw=4 sts=4 et ft=python
"""Ansible inventory plugin for retrieving all the kubevirt VMs

Use it by enabling `kubevirt_vms` in ansible.cfg and then add oc.yml
to your inventory with the following content:

```
plugin: kubevirt_vms
```

This plugin configures the vms to use the virtctl connection plugin
by default.
"""
from __future__ import absolute_import

from six import iteritems

from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable

from kubernetes import config
from openshift.dynamic import DynamicClient

# HACK import the inventory plugin openshift_nodes while running in Ansible
import imp
import os.path

openshift_nodes = imp.load_source(
    "openshift_nodes", os.path.join(os.path.dirname(__file__), "openshift_nodes.py")
)
ansible_annotation_vars = openshift_nodes.ansible_annotation_vars
dict_merge = openshift_nodes.dict_merge


def first_ip(vmi):
    return next(
        intf.ipAddress
        for intf in vmi.status.interfaces
        if (
            intf.ipAddress != "127.0.0.1"
            and any(
                s.status == "True" and s.type == "Ready" for s in vmi.status.conditions
            )
        )
    )


def ssh_vars(vmi):
    ssh_vars = {}
    if vmi.status.interfaces:
        ssh_vars.update({"ansible_ssh_host": first_ip(vmi)})
    return ssh_vars


def vmi_entry(vmi, extra_ssh_args):
    """Converts a VMI instance into a host dict that is better suited
       for the ansible inventory generator."""
    return {
        "name": vmi.metadata.name if vmi.metadata.name != "localhost" else "vm",
        "namespace": vmi.metadata.namespace,
        "groups": ["kubevirt-" + vmi.metadata.namespace],
        "vars": dict_merge(
            {
                "virtctl_name": vmi.metadata.name,
                "virtctl_namespace": vmi.metadata.namespace,
                "ansible_connection": "virtctl",
                "ansible_ssh_extra_args": extra_ssh_args,
                "ansible_become": False,
                "ansible_user": "root",
                "ansible_become_method": "sudo",
                "ansible_ssh_pass": "unknown",
            },
            ansible_annotation_vars(vmi.metadata.annotations),
            ssh_vars(vmi),
        ),
    }


def get_vms():
    k8s_client = config.new_client_from_config()
    dyn_client = DynamicClient(k8s_client)

    v1_vmis = dyn_client.resources.get(
        api_version="kubevirt.io/v1alpha3", kind="VirtualMachineInstance"
    )

    v1_vmi_list = v1_vmis.get()
    vmi_details = [vmi for vmi in v1_vmi_list.items]

    # Find a master node and get SSH proxy options
    # from it. This is needed to connect to minishift VMs
    # as they are hidden withing the minishift host virtual machine
    master_nodes = [
        node for node in openshift_nodes.get_nodes() if "master" in node["groups"]
    ]
    master_node = master_nodes[0]
    extra_ssh_args = master_node.get("vars", {}).get("ssh_via_arguments", "")

    return [vmi_entry(vmi, extra_ssh_args) for vmi in vmi_details]


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = "kubevirt_vms"

    def verify_file(self, path):
        """ return true/false if this is possibly a valid file for this plugin to consume """
        # base class verifies that file exists and is readable by current user
        return super(InventoryModule, self).verify_file(path) and path.endswith(
            ("kubevirt.yaml", "kubevirt.yml")
        )

    def parse(self, inventory, loader, path, cache=True):
        # call base method to ensure properties are available for use with other helper methods
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        # this method will parse 'common format' inventory sources and
        # update any options declared in DOCUMENTATION as needed
        config = self._read_config_data(path)

        def host_name(h):
            return config.get("host_format", "{namespace}-{name}").format(**h)

        for vm in get_vms():
            name = host_name(vm)
            self.inventory.add_host(name)
            for k, v in iteritems(vm["vars"]):
                self.inventory.set_variable(name, k, v)
            for group in vm["groups"]:
                self.inventory.add_group(group)
                self.inventory.add_child(group, name)
            for group in config.get("keyed_groups", []):
                self.inventory.add_group(group)
                self.inventory.add_child(group, name)
