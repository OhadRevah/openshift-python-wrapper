import logging
import os

from ocp_resources.datavolume import DataVolume
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.project import ProjectRequest
from ocp_resources.service import Service
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import config as py_config

import utilities.infra
from utilities.constants import MACHINE_CONFIG_PODS_TO_COLLECT, PODS_TO_COLLECT_INFO


LOGGER = logging.getLogger(__name__)


def collect_vmi_data(vmi, directory=None):
    write_to_file(
        file_name=f"vmi-{vmi.name}.yaml",
        content=vmi.instance.to_str(),
        base_directory=directory,
    )

    virt_launcher_pod = vmi.virt_launcher_pod
    write_to_file(
        file_name=f"{virt_launcher_pod.name}.log",
        content=virt_launcher_pod.log(container="compute"),
        base_directory=directory,
    )
    write_to_file(
        file_name=f"{virt_launcher_pod.name}.yaml",
        content=virt_launcher_pod.instance.to_str(),
        base_directory=directory,
    )


def collect_data_volume_data(dyn_client, directory=None):
    cdi_pod_prefixes = ("importer", "cdi-upload")
    for pod in Pod.get(dyn_client=dyn_client):
        pod_name = pod.name
        if pod_name.startswith(cdi_pod_prefixes) or pod_name.endswith("source-pod"):
            write_to_file(
                file_name=f"{pod_name}.log", content=pod.log(), base_directory=directory
            )
            write_to_file(
                file_name=f"{pod_name}.yaml",
                content=pod.instance.to_str(),
                base_directory=directory,
            )


def collect_data(directory, resource_object):
    LOGGER.info(f"Collecting instance data for {resource_object.name}")

    if resource_object.kind == ProjectRequest.kind:
        resource_object = Namespace(name=resource_object.name)

    write_to_file(
        file_name=f"{resource_object.name}.yaml",
        content=resource_object.instance.to_str(),
        base_directory=directory,
    )
    if resource_object.kind == VirtualMachine.kind and resource_object.vmi:
        collect_vmi_data(vmi=resource_object.vmi, directory=directory)

    if resource_object.kind == DataVolume.kind:
        collect_data_volume_data(dyn_client=resource_object.client, directory=directory)


def prepare_test_data_dir(item, prefix, logs_path=None):
    test_cls_name = item.cls.__name__ if item.cls else ""
    test_dir_log = os.path.join(
        logs_path or py_config["data_collector"]["data_collector_base_directory"],
        item.fspath.dirname.split("/tests/")[-1],
        item.fspath.basename.partition(".py")[0],
        test_cls_name,
        item.name,
        prefix,
    )
    os.makedirs(test_dir_log, exist_ok=True)
    return test_dir_log


def collect_resources_yaml_instance(resources_to_collect, namespace_name=None):
    get_kwargs = {"dyn_client": utilities.infra.get_admin_client()}
    for _resources in resources_to_collect:
        if _resources == Service:
            get_kwargs["namespace"] = namespace_name

        for resource_obj in _resources.get(**get_kwargs):
            try:
                write_to_file(
                    file_name=f"{resource_obj.name}.yaml",
                    content=resource_obj.instance.to_str(),
                    extra_dir_name=resource_obj.kind,
                )
            except Exception as exp:
                LOGGER.warning(
                    f"Failed to collect resource: {resource_obj.kind} {resource_obj.name} {exp}"
                )


def collect_pods_data(pods, pod_list=None):
    pod_list = pod_list or PODS_TO_COLLECT_INFO
    for pod in pods:
        kwargs = {}
        for pod_prefix in pod_list:
            if pod.name.startswith(pod_prefix):
                if pod_prefix == "virt-launcher":
                    kwargs = {"container": "compute"}
                if pod_prefix in MACHINE_CONFIG_PODS_TO_COLLECT:
                    kwargs = {"container": pod_prefix}

                write_to_file(
                    file_name=f"{pod.name}.log",
                    content=pod.log(**kwargs),
                    extra_dir_name=pod.kind,
                )
                write_to_file(
                    file_name=f"{pod.name}.yaml",
                    content=pod.instance.to_str(),
                    extra_dir_name=pod.kind,
                )


def write_to_file(file_name, content, base_directory=None, extra_dir_name=None):
    """
    This will write to a file that will be available after the run execution.

    Args:
        file_name (string): name of the file to write.
        content (string): the content of the file to write.
        base_directory (string): the base directory to write the file to.
        extra_dir_name (string): (optional) the directory name to create inside base_directory.
    """
    bash_dir = base_directory or os.environ.get(
        "OPENSHIFT_PYTHON_WRAPPER_DATA_COLLECTOR_YAML",
        py_config.get("data_collector", {}).get(
            "data_collector_base_directory", "data-collected-info"
        ),
    )

    os.makedirs(bash_dir, exist_ok=True)
    if extra_dir_name:
        extras_dir = os.path.join(bash_dir, extra_dir_name)
        os.makedirs(extras_dir, exist_ok=True)
        file_path = os.path.join(extras_dir, file_name)
    else:
        file_path = os.path.join(bash_dir, file_name)
    try:
        with open(file_path, "w") as fd:
            fd.write(content)
    except Exception as exp:
        LOGGER.warning(f"Failed to write extras to file: {file_path} {exp}")


def collect_mcp_information():
    LOGGER.warning("Collecting MachineConfigPool data for triage.")
    collect_resources_yaml_instance(resources_to_collect=[MachineConfigPool, Node])
    pods = utilities.infra.get_pods(
        dyn_client=utilities.infra.get_admin_client(),
        namespace=utilities.infra.cluster_resource(Namespace)(
            name="openshift-machine-config-operator"
        ),
    )
    collect_pods_data(pods=pods, pod_list=MACHINE_CONFIG_PODS_TO_COLLECT)
