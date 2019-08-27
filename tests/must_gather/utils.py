# -*- coding: utf-8 -*-


import os
import yaml
from openshift.dynamic.client import ResourceField

DEFAULT_NAMESPACE = "default"


def resources_match(resource_field, file_part):
    if type(resource_field) != ResourceField:
        return resource_field == file_part
    resource_field_keys = resource_field.keys()
    if not resource_field_keys == file_part.keys():
        return False
    for k in resource_field_keys:
        if not resources_match(getattr(resource_field, k), file_part[k]):
            return False
    return True


def compare_resources(resource, path, checks):
    with open(path) as resource_file:
        file_content = yaml.load(resource_file.read(), Loader=yaml.FullLoader)
    for check in checks:
        oc_part = resource.instance
        file_part = file_content

        for part in check:
            oc_part = getattr(oc_part, part)
            file_part = file_part[part]
        if not resources_match(oc_part, file_part):
            raise Exception(
                f"Comparison of resource {resource.name} "
                f"(namespace: {resource.namespace}) "
                f"failed for element {check}."
                f"Mismatched values: \n {oc_part}\n{file_part}"
            )


def check_list_of_resources(
    default_client, resource_type, temp_dir, resource_path, checks
):
    for resource in resource_type.get(default_client):
        ns = resource.namespace or DEFAULT_NAMESPACE
        path = os.path.join(
            temp_dir, resource_path.format(name=resource.name, namespace=ns)
        )
        compare_resources(resource, path, checks)
