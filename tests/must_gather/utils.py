# -*- coding: utf-8 -*-


import os

import yaml
from openshift.dynamic.client import ResourceField
from pytest_testconfig import config as py_config


DEFAULT_NAMESPACE = "default"
HCO_NS = py_config["hco_namespace"]


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


def _pod_logfile_path(pod_name, container_name, previous, cnv_must_gather_path):
    log = "previous" if previous else "current"
    return (
        f"{cnv_must_gather_path}/namespaces/{HCO_NS}/pods/{pod_name}/"
        f"{container_name}/{container_name}/logs/{log}.log"
    )


def pod_logfile(pod_name, container_name, previous, cnv_must_gather_path):
    with open(
        _pod_logfile_path(pod_name, container_name, previous, cnv_must_gather_path)
    ) as log_file:
        return log_file.read()


def pod_logfile_size(pod_name, container_name, previous, cnv_must_gather_path):
    return os.path.getsize(
        _pod_logfile_path(pod_name, container_name, previous, cnv_must_gather_path)
    )


def filter_pods(running_hco_containers, labels):
    for pod, container in running_hco_containers:
        for k, v in labels.items():
            if pod.labels.get(k) == v:
                yield pod, container


def check_logs(cnv_must_gather, running_hco_containers, label_selector):
    for pod, container in filter_pods(running_hco_containers, label_selector):
        container_name = container["name"]
        for is_previous in (True, False):
            log_size = pod_logfile_size(
                pod.name, container_name, is_previous, cnv_must_gather
            )
            # Skip comparison of empty/large files. Large files could be ratated, and hence not equal.
            if log_size > 10000 or log_size == 0:
                continue
            pod_log = pod.log(
                previous=is_previous, container=container_name, timestamps=True
            )
            log_file = pod_logfile(
                pod.name, container_name, is_previous, cnv_must_gather
            )
            assert (
                log_file in pod_log
            ), f"Log file are different for pod/container {pod.name}/{container_name}"
