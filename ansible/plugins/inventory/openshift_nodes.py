#!/usr/bin/env python
# vim: sw=4 sts=4 et ft=python
"""Ansible inventory plugin to get openshift nodes from a running cluster.

Use it by enabling `openshift_nodes` in ansible.cfg and then add oc.yml
to your inventory with the following content:

```
plugin: openshift_nodes
```
"""

from __future__ import absolute_import

import json

from ansible.plugins.inventory import BaseInventoryPlugin
from kubernetes import config
from openshift.dynamic import DynamicClient
from six import iteritems


def ansible_annotation_vars(annotations):
    if annotations is None:
        return {}
    return json.loads(annotations.get("ansible", "{}"))


def dict_merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


def compute_groups(labels):
    groups = []
    for k, v in iteritems(labels):
        if k.startswith("node-role.kubernetes.io/") and v:
            groups.append(k.split("/")[1])

    return groups or ["master", "infra", "worker"]


def get_nodes():
    k8s_client = config.new_client_from_config()
    dyn_client = DynamicClient(k8s_client)

    v1_nodes = dyn_client.resources.get(api_version="v1", kind="Node")
    v1_node_list = v1_nodes.get()
    node_details = [node for node in v1_node_list.items]

    def first_ip(node):
        return next(
            addr.address
            for addr in node.status.addresses
            if (addr.address != "localhost" and addr.address != "127.0.0.1")
        )

    nodes = [
        {
            "name": node.metadata.name if node.metadata.name != "localhost" else "node",
            "groups": ["cnv"] + compute_groups(node.metadata.labels or {}),
            "vars": dict_merge(
                {
                    "ansible_ssh_host": first_ip(node),
                    "ansible_become": True,
                    "ansible_become_method": "sudo",
                    # Enable for minishift
                    # "ansible_user": "docker",
                    # "ansible_ssh_private_key_file": "~/.minishift/machines/minishift/id_rsa",
                    # "ssh_via_arguments": """
                    #      -o UserKnownHostsFile=/dev/null
                    #      -o StrictHostKeyChecking=no
                    #      -o 'ProxyCommand ssh -o UserKnownHostsFile=/dev/null
                    #                           -o StrictHostKeyChecking=no
                    #                           -W %h:%p
                    #                           -i ~/.minishift/machines/minishift/id_rsa
                    #                           docker@""" + first_ip(node) + "'"
                },
                ansible_annotation_vars(node.metadata.annotations),
            ),
        }
        for node in node_details
    ]

    return nodes


class InventoryModule(BaseInventoryPlugin):
    NAME = "openshift_nodes"  # used internally by Ansible, it should match the file name but not required

    def verify_file(self, path):
        """ return true/false if this is possibly a valid file for this plugin to consume """
        # base class verifies that file exists and is readable by current user
        return super(InventoryModule, self).verify_file(path) and path.endswith(
            (
                "openshift.yaml",
                "openshift.yml",
                "minishift.yaml",
                "minishift.yml",
                "oc.yaml",
                "oc.yml",
            )
        )

    def parse(self, inventory, loader, path, cache=True):
        # call base method to ensure properties are available for use with other helper methods
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        # This method will parse 'common format' inventory sources and
        # update any options declared in DOCUMENTATION as needed
        # Enable the following line once that is needed.
        # config = self._read_config_data(path)

        for node in get_nodes():
            self.inventory.add_host(node["name"])
            for k, v in iteritems(node["vars"]):
                self.inventory.set_variable(node["name"], k, v)
            for group in node["groups"]:
                self.inventory.add_group(group)
                self.inventory.add_child(group, node["name"])
