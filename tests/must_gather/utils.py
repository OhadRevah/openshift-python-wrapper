# -*- coding: utf-8 -*-

import difflib
import os
import re

import yaml
from openshift.dynamic.client import ResourceField
from resources.service import Service


DEFAULT_NAMESPACE = "default"
SRIOV_NETWORK_OPERATOR_NAMESPACE = "sriov-network-operator"


class ResourceMissMatch(Exception):
    pass


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
        file_content = yaml.load(resource_file.read(), Loader=yaml.Loader)
    compare_resource_contents(
        resource=resource, file_content=file_content, checks=checks
    )


def compare_resource_contents(resource, file_content, checks):
    for check in checks:
        oc_part = resource.instance
        file_part = file_content

        for part in check:
            oc_part = getattr(oc_part, part)
            file_part = file_part[part]
        with ResourceFieldEqBugWorkaround():
            if oc_part != file_part:
                raise ResourceMissMatch(
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
    compare_resource_values(resource=resource_instance, path=path, checks=checks)


def check_list_of_resources(
    dyn_client,
    resource_type,
    temp_dir,
    resource_path,
    checks,
    namespace=None,
    label_selector=None,
    filter_resource=None,
):
    for resource_instance in resource_type.get(
        dyn_client, namespace=namespace, label_selector=label_selector
    ):
        if filter_resource is None or filter_resource in resource_instance.name:
            compare_resources(
                resource_instance=resource_instance,
                temp_dir=temp_dir,
                resource_path=resource_path,
                checks=checks,
            )


def check_resource(resource, resource_name, temp_dir, resource_path, checks):
    resource_instance = resource(name=resource_name)
    compare_resources(
        resource_instance=resource_instance,
        temp_dir=temp_dir,
        resource_path=resource_path,
        checks=checks,
    )


class NodeResourceException(Exception):
    def __init__(self, diff):
        self.diff = diff

    def __str__(self):
        return (
            "File content created by must-gather is different from the expected command output:\n"
            f"{''.join(self.diff)}"
        )


def remove_veth_ifaces(raw_str):
    raw_ifaces = re.split(r"(^\d+:|\n\d+:)", raw_str)
    # re.split can produce unnecessary empty strings so delete them:
    raw_ifaces = list(filter(None, raw_ifaces))
    clean_ifaces = [
        f"{num}{iface}"
        for num, iface in zip(raw_ifaces[::2], raw_ifaces[1::2])
        if "veth" not in iface
    ]
    return "".join(clean_ifaces)


def clean_ip_data(raw_str):
    """
    Remove data that can cause diffs we want to ignore:
    - veth interfaces can come and go any time and their names are random
    - properties 'dynamic' and 'noprefixroute' sometimes appear in different order
    - line with 'valid_lft' and 'preferred_lft' info shows different times when not set to 'forever'
    - inet6 info is inconsistent. try again with it when dual-stack is supported
    """
    clean_str = remove_veth_ifaces(raw_str=raw_str)
    clean_str = clean_str.replace("dynamic", "").replace("noprefixroute", "")
    return [
        line
        for line in clean_str.splitlines(keepends=True)
        if "valid_lft" not in line and "inet6" not in line
    ]


def nft_chains(raw_str):
    return [
        line for line in raw_str.splitlines(keepends=True) if line.startswith("\tchain")
    ]


def compare_node_data(file_content, cmd_output, compare_method):
    if compare_method == "simple_compare":
        diff = list(
            difflib.ndiff(
                file_content.splitlines(keepends=True),
                cmd_output.splitlines(keepends=True),
            )
        )
    elif compare_method == "ip_compare":
        diff = list(
            difflib.ndiff(
                clean_ip_data(raw_str=file_content),
                clean_ip_data(raw_str=cmd_output),
            )
        )
    elif compare_method == "nft_compare":
        diff = list(
            difflib.ndiff(
                nft_chains(raw_str=file_content),
                nft_chains(raw_str=cmd_output),
            )
        )
    else:
        raise NotImplementedError(f"{compare_method} not implemented")

    if any(line.startswith(("- ", "+ ")) for line in diff):
        raise NodeResourceException(diff)


def check_node_resource(temp_dir, cmd, utility_pod, results_file, compare_method):
    cmd_output = utility_pod.execute(command=cmd)
    file_name = f"{temp_dir}/nodes/{utility_pod.node.name}/{results_file}"
    with open(file_name) as result_file:
        file_content = result_file.read()
        compare_node_data(
            file_content=file_content,
            cmd_output=cmd_output,
            compare_method=compare_method,
        )


def _pod_logfile_path(
    pod_name, container_name, previous, cnv_must_gather_path, namespace
):
    log = "previous" if previous else "current"
    return (
        f"{cnv_must_gather_path}/namespaces/{namespace}/pods/{pod_name}/"
        f"{container_name}/{container_name}/logs/{log}.log"
    )


def pod_logfile(pod_name, container_name, previous, cnv_must_gather_path, namespace):
    with open(
        _pod_logfile_path(
            pod_name, container_name, previous, cnv_must_gather_path, namespace
        )
    ) as log_file:
        return log_file.read()


def pod_logfile_size(
    pod_name, container_name, previous, cnv_must_gather_path, namespace
):
    return os.path.getsize(
        _pod_logfile_path(
            pod_name, container_name, previous, cnv_must_gather_path, namespace
        )
    )


def filter_pods(running_hco_containers, labels):
    for pod, container in running_hco_containers:
        for k, v in labels.items():
            if pod.labels.get(k) == v:
                yield pod, container


def check_logs(cnv_must_gather, running_hco_containers, label_selector, namespace):
    for pod, container in filter_pods(running_hco_containers, label_selector):
        container_name = container["name"]
        for is_previous in (True, False):
            log_size = pod_logfile_size(
                pod_name=pod.name,
                container_name=container_name,
                previous=is_previous,
                cnv_must_gather_path=cnv_must_gather,
                namespace=namespace,
            )
            # Skip comparison of empty/large files. Large files could be ratated, and hence not equal.
            if log_size > 10000 or log_size == 0:
                continue
            pod_log = pod.log(
                previous=is_previous, container=container_name, timestamps=True
            )
            log_file = pod_logfile(
                pod_name=pod.name,
                container_name=container_name,
                previous=is_previous,
                cnv_must_gather_path=cnv_must_gather,
                namespace=namespace,
            )
            assert (
                log_file in pod_log
            ), f"Log file are different for pod/container {pod.name}/{container_name}"


def compare_webhook_svc_contents(
    webhook_resources, cnv_must_gather, dyn_client, checks
):
    for webhook_resource in webhook_resources:
        if webhook_resource.kind == "MutatingWebhookConfiguration":
            service_file = os.path.join(
                cnv_must_gather,
                f"webhooks/mutating/{webhook_resource.name}/service.yaml",
            )
        elif webhook_resource.kind == "ValidatingWebhookConfiguration":
            service_file = os.path.join(
                cnv_must_gather,
                f"webhooks/validating/{webhook_resource.name}/service.yaml",
            )
        webhooks_resource_instance = webhook_resource.instance.webhooks
        webhooks_svc_name = webhooks_resource_instance[0]["clientConfig"]["service"][
            "name"
        ]
        webhooks_svc_namespace = webhooks_resource_instance[0]["clientConfig"][
            "service"
        ]["namespace"]
        svc_resources = list(Service.get(dyn_client, namespace=webhooks_svc_namespace))
        for svc_resource in svc_resources:
            if webhooks_svc_name == svc_resource.name:
                compare_resource_values(
                    resource=svc_resource, path=service_file, checks=checks
                )


def get_log_dir(path):
    for item in os.listdir(path):
        new_path = os.path.join(path, item)
        if os.path.isdir(new_path):
            return new_path
    raise FileNotFoundError(f"No log directory was created in '{path}'")


def assert_nft_collection(nft_files, nftables, node_name):
    assert len(nft_files) == len(nftables), (
        "difference in number of collected nftables\n"
        f"node: {node_name}\n"
        f"must-gather collected nftables: {nft_files}\n"
        f"utility-pod collected nftables: {nftables}"
    )
