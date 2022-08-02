import ast
import importlib
import os
import re

from ocp_resources.pod import Pod
from ocp_resources.replicaset import ReplicaSet
from ocp_resources.resource import NamespacedResource, Resource

from utilities.exceptions import LeftoversFoundError
from utilities.infra import LOGGER


def get_resource_classes(tree):
    exclude_classes = (
        "Resource",
        "NamespacedResource",
        "Event",
        "MTV",
        "UploadTokenRequest",
        "ProjectRequest",
    )
    for _resource_class in [cls for cls in tree.body if isinstance(cls, ast.ClassDef)]:
        if _resource_class.name in exclude_classes:
            continue
        yield _resource_class


def get_class_object(resource_import, _cls):
    cls_obj = getattr(resource_import, _cls.name)
    if hasattr(cls_obj, "get") and any(
        _cls for _cls in cls_obj.mro() if _cls in (NamespacedResource, Resource)
    ):
        return cls_obj


def get_resources_object(admin_client, cls_obj):
    exclude_resources_prefix = (
        "deployer-",
        "default-",
        "builder-",
        "olm-operator-heap",
        "catalog-operator-heap",
        "collect-profiles",
    )
    excluded_namespaces = (
        "openshift-marketplace",
        "openshift-image-registry",
        "openshift-operator-lifecycle-manager",
    )

    if cls_obj:
        for resource in cls_obj.get(dyn_client=admin_client):
            if resource.name.startswith(exclude_resources_prefix):
                continue
            if resource.namespace in excluded_namespaces:
                continue
            yield resource


def collect_resource(results_dict, resource):
    # Pod and ReplicaSet resources have generated names, the key is some static name.
    if resource.kind in (Pod.kind, ReplicaSet.kind):
        owner_references = resource.instance.metadata.ownerReferences
        name_key = (
            owner_references[0].name
            if owner_references
            else resource.labels.app or resource.name
        )
        results_dict.setdefault(resource.kind, {}).setdefault(
            name_key,
            [],
        ).append(resource.name)

    else:
        results_dict.setdefault(resource.kind, []).append(resource)


def get_cluster_resources(admin_client, resource_files_path):
    import ocp_resources  # noqa: F401

    results_dict = {}
    for _file in resource_files_path:
        with open(_file, "r") as fd:
            file_data = fd.read()

        resource_path = re.sub(r"\.py$", "", f"ocp_resources.{os.path.basename(_file)}")
        resource_import = importlib.import_module(name=resource_path)

        for _cls in get_resource_classes(tree=ast.parse(source=file_data)):
            try:
                cls_obj = get_class_object(resource_import=resource_import, _cls=_cls)
                for _resource in get_resources_object(
                    admin_client=admin_client, cls_obj=cls_obj
                ):
                    collect_resource(results_dict=results_dict, resource=_resource)

            except Exception as exp:
                if "Couldn't find" not in exp.__str__():
                    LOGGER.warning(
                        f"Failed to get {_cls.name} resources from {_file} due to {exp}"
                    )
                continue
    return results_dict


def check_leftovers_by_kind(resource_kind, items, leftovers, cluster_resources):
    for app, resource_list in items.items():
        if resource_list and len(resource_list) != len(
            cluster_resources[resource_kind][app]
        ):
            leftovers.setdefault(resource_kind, []).extend(resource_list)
    return leftovers


def raise_for_leftover(leftovers):
    leftovers_log = "\n"
    for _kind, _leftover in leftovers.items():
        leftovers_log += f"[{_kind}] "
        for _resource in _leftover:
            leftovers_log += f"\t[Name]: {_resource.name} [Namespace]: {_resource.namespace or 'None'}\n"
    raise LeftoversFoundError(leftovers_log)


def check_for_leftovers(admin_client, ocp_resources_files_path, cluster_resources):
    found_leftovers = {}
    collected_resources = get_cluster_resources(
        admin_client=admin_client, resource_files_path=ocp_resources_files_path
    )

    for key, value in collected_resources.items():
        if not cluster_resources.get(key):
            found_leftovers.setdefault(key, []).extend(value)

        else:
            if key in (Pod.kind, ReplicaSet.kind):
                found_leftovers = check_leftovers_by_kind(
                    resource_kind=key,
                    items=value,
                    leftovers=found_leftovers,
                    cluster_resources=cluster_resources,
                )
            else:
                _leftovers = [
                    _resource
                    for _resource in value
                    if _resource.name
                    not in [
                        before_resource_name.name
                        for before_resource_name in cluster_resources[key]
                    ]
                ]
                if _leftovers:
                    found_leftovers.setdefault(key, []).extend(_leftovers)

    if found_leftovers:
        raise_for_leftover(leftovers=found_leftovers)
