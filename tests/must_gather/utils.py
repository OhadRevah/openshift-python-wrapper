# -*- coding: utf-8 -*-


import os

import yaml
from openshift.dynamic.client import ResourceField


DEFAULT_NAMESPACE = "default"


# TODO: this is a workaround for an openshift bug
# An issue was opened in openshift for this:
# https://github.com/openshift/openshift-restclient-python/issues/320
# To be removed after the issue is fixed in openshift
class ResourceFieldEqBugWorkaround(object):
    def __enter__(self):
        self.prev_eq_func = ResourceField.__eq__

        def new_eq_func(self, other):
            if type(other) == dict:
                return self.__dict__ == other
            return self.prev_eq_func(self, other)

        ResourceField.__eq__ = new_eq_func

    def __exit__(self, *args):
        ResourceField.__eq__ = self.prev_eq_func


def compare_resource_values(resource, path, checks):
    with open(path) as resource_file:
        file_content = yaml.load(resource_file.read(), Loader=yaml.FullLoader)
    for check in checks:
        oc_part = resource.instance
        file_part = file_content

        for part in check:
            oc_part = getattr(oc_part, part)
            file_part = file_part[part]
        with ResourceFieldEqBugWorkaround():
            if oc_part != file_part:
                raise Exception(
                    f"Comparison of resource {resource.name} "
                    f"(namespace: {resource.namespace}) "
                    f"failed for element {check}."
                    f"Mismatched values: \n {oc_part}\n{file_part}"
                )


def compare_resources(resource_instance, temp_dir, resource_path, checks):
    path = os.path.join(
        temp_dir,
        resource_path.format(
            name=resource_instance.name,
            namespace=resource_instance.namespace or DEFAULT_NAMESPACE,
        ),
    )
    compare_resource_values(resource_instance, path, checks)


def check_list_of_resources(
    default_client,
    resource_type,
    temp_dir,
    resource_path,
    checks,
    namespace=None,
    label_selector=None,
):
    for resource_instance in resource_type.get(
        default_client, namespace=namespace, label_selector=label_selector
    ):
        compare_resources(resource_instance, temp_dir, resource_path, checks)


def check_resource(resource, resource_name, temp_dir, resource_path, checks):
    resource_instance = resource(name=resource_name)
    compare_resources(resource_instance, temp_dir, resource_path, checks)


def check_node_resource(temp_dir, cmd, node_gather_pods, results_file):
    for pod in node_gather_pods:
        cmd_output = pod.execute(command=cmd)
        file_name = f"{temp_dir}/nodes/{pod.node.name}/{results_file}"
        with open(file_name) as result_file:
            file_content = result_file.read()
            assert file_content == cmd_output
