import datetime
import logging
import os
import re
import shlex
from collections import Counter

import pytest
import yaml
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.os_params import (
    FEDORA_LATEST,
    FEDORA_LATEST_LABELS,
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
)
from utilities.constants import (
    OS_FLAVOR_FEDORA,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WINDOWS,
    TIMEOUT_1MIN,
    TIMEOUT_30MIN,
)
from utilities.infra import create_ns, run_cnv_must_gather
from utilities.storage import generate_data_source_dict, get_images_server_url
from utilities.virt import VirtualMachineForTestsFromTemplate, run_command


LOGGER = logging.getLogger(__name__)
OCS = "ocs"
NFS = "nfs"

SCALE_STORAGE_TYPES = {
    OCS: StorageClass.Types.CEPH_RBD,
    NFS: StorageClass.Types.NFS,
}
pytestmark = pytest.mark.scale


def log_nodes_load_data(vms):
    """
    Log the distribution of VM's on the nodes, and the cluster memory/cpu statistics

    Args:
        vms (list): List of vms to log statistics on
    """
    nodes_load_distribute = Counter([vm.vmi.node.name for vm in vms])
    LOGGER.info(f"Nodes vm load distribution: {nodes_load_distribute}")
    nodes_load_statistics = run_command(command=shlex.split("oc adm top nodes"))
    LOGGER.info(f"Nodes load statistics:\n {nodes_load_statistics[1]}")


def all_vms_running(vms):
    """
    Check if all VMIs are in running state

    Args:
        vms (list): List of vms to verify

    Returns:
        bool: True if all vms in running state, False otherwise
    """
    num_of_running_vms = len(vm for vm in vms if vm.vmi.status == vm.Status.RUNNING)
    LOGGER.info(f"Number of running vms: {num_of_running_vms}")
    return num_of_running_vms == len(vms)


def delete_resources(namespace, vms, scale_dvs, data_sources):
    """
    Delete the test resources that were created

    Args:
        namespace (Project): the test Project object
        vms (list): the test vms
        scale_dvs (list): the test dvs
        data_sources (dict): the test data sources
    """
    all_resources_list = list(data_sources.values()) + scale_dvs + vms
    for _resource in all_resources_list:
        _resource.delete()
    for _resource in all_resources_list:
        _resource.wait_deleted()
    namespace.clean_up()


def create_and_start_scale_vm(
    data_source, vm_info, os_type, storage, vm_index, namespace, client
):
    scale_vm = VirtualMachineForTestsFromTemplate(
        name=f"vm-{os_type}-{storage}-{vm_index}",
        namespace=namespace.name,
        client=client,
        cpu_cores=vm_info["cores"],
        memory_requests=vm_info["memory"],
        data_source=data_source,
        labels=Template.generate_template_labels(**vm_info["latest_labels"]),
    )
    scale_vm.deploy()
    scale_vm.start(wait=True)
    return scale_vm


def save_must_gather_logs(must_gather_image_url):
    logs_path = os.path.join(
        os.path.expanduser("~"),
        f"must_gather_{datetime.datetime.utcnow().strftime('%Y_%m_%d_%H_%M_%S')}",
    )
    os.makedirs(logs_path)
    return run_cnv_must_gather(image_url=must_gather_image_url, dest_dir=logs_path)


def failure_finalizer(vms_list, must_gather_image_url):
    log_nodes_load_data(vms=vms_list)
    logs_folders = save_must_gather_logs(must_gather_image_url=must_gather_image_url)
    pytest.fail(
        msg=f"Test failed, keeping the test environment. the must-gather logs are saved under {logs_folders}"
    )


@pytest.fixture(scope="module")
def fail_if_param_vms_zero(expected_num_of_vms):
    if expected_num_of_vms == 0:
        pytest.fail("The sum of the VMs number in the scale_params.yaml file is 0")


@pytest.fixture(scope="module")
def expected_num_of_vms(scale_test_param):
    """
    The amount of vms to create and start that were configured in the yaml file

    Args:
        scale_test_param (dict): Parameters dictionary of scale_params.yaml

    Returns:
        int: amount of total vms that should start
    """
    return sum(
        [
            sum(
                [
                    os_vms[storage_type_key]["vms"]
                    for storage_type_key in SCALE_STORAGE_TYPES
                ]
            )
            for os_vms in scale_test_param["vms"].values()
        ]
    )


@pytest.fixture(scope="module")
def scale_test_param(pytestconfig):
    with open(pytestconfig.option.scale_params_file) as params_file:
        return yaml.safe_load(stream=params_file)


@pytest.fixture(scope="module")
def scale_namespace(unprivileged_client, scale_test_param):
    yield from create_ns(
        name=scale_test_param["test_namespace"],
        teardown=False,
        unprivileged_client=unprivileged_client,
    )


@pytest.fixture(scope="module")
def dvs_os_info():
    return {
        OS_FLAVOR_RHEL: {
            "url": RHEL_LATEST["image_path"],
            "size": RHEL_LATEST["dv_size"],
        },
        OS_FLAVOR_FEDORA: {
            "url": FEDORA_LATEST["image_path"],
            "size": FEDORA_LATEST["dv_size"],
        },
        OS_FLAVOR_WINDOWS: {
            "url": WINDOWS_LATEST["image_path"],
            "size": WINDOWS_LATEST["dv_size"],
        },
    }


@pytest.fixture(scope="module")
def dvs_info(scale_test_param, dvs_os_info):
    dvs_info = {}
    for os_name in dvs_os_info:
        dvs_info.update(
            {
                os_name: {
                    OCS: {"vms": scale_test_param["vms"][os_name][OCS]["vms"]},
                    NFS: {"vms": scale_test_param["vms"][os_name][NFS]["vms"]},
                }
            }
        )
        dvs_info[os_name].update(dvs_os_info[os_name])
    return dvs_info


@pytest.fixture(scope="module")
def vms_info(scale_test_param):
    vms_info_dict = {
        OS_FLAVOR_RHEL: {"latest_labels": RHEL_LATEST_LABELS},
        OS_FLAVOR_FEDORA: {"latest_labels": FEDORA_LATEST_LABELS},
        OS_FLAVOR_WINDOWS: {"latest_labels": WINDOWS_LATEST_LABELS},
    }
    for os_name in vms_info_dict:
        for storage_type_key in SCALE_STORAGE_TYPES:
            vms_info_dict[os_name][storage_type_key] = {
                "vms": scale_test_param["vms"][os_name][storage_type_key]["vms"]
            }
        vms_info_dict[os_name]["cores"] = int(scale_test_param["vms"][os_name]["cores"])
        vms_info_dict[os_name]["memory"] = scale_test_param["vms"][os_name]["memory"]
    return vms_info_dict


@pytest.fixture(scope="module")
def scale_dvs(admin_client, golden_images_namespace, dvs_info):
    dvs_list = []
    for os_name, dv_info in dvs_info.items():
        storage_types_used = [
            storage_type_key
            for storage_type_key in SCALE_STORAGE_TYPES
            if dv_info[storage_type_key]["vms"]
        ]
        for storage_type in storage_types_used:
            scale_dv = DataVolume(
                name=f"{os_name}-{storage_type}-dv",
                namespace=golden_images_namespace.name,
                storage_class=SCALE_STORAGE_TYPES[storage_type],
                api_name="storage",
                url=f"{get_images_server_url(schema='http')}{dv_info['url']}",
                size=dv_info["size"],
                client=admin_client,
                source="http",
            )
            scale_dv.deploy()
            dvs_list.append(scale_dv)
    for dv in dvs_list:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=TIMEOUT_30MIN)
    return dvs_list


@pytest.fixture(scope="module")
def data_sources(admin_client, scale_dvs):
    data_sources = {}
    for dv in scale_dvs:
        ds_name = re.sub(r"-dv", r"-ds", dv.name)
        data_source = DataSource(
            name=ds_name,
            namespace=dv.namespace,
            client=admin_client,
            source=generate_data_source_dict(dv=dv),
        )
        data_source.deploy()
        data_sources.update({data_source.name: data_source})
    return data_sources


@pytest.fixture(scope="module")
def vms(
    unprivileged_client,
    data_sources,
    scale_namespace,
    vms_info,
    must_gather_image_url,
):
    vms_list = []

    for os_type, info in vms_info.items():
        for storage_type_key in SCALE_STORAGE_TYPES:
            num_of_vms = info[storage_type_key]["vms"]
            for vm_index in range(num_of_vms):
                try:
                    vms_list.append(
                        create_and_start_scale_vm(
                            data_source=data_sources[
                                f"{os_type}-{storage_type_key}-ds"
                            ],
                            vm_info=info,
                            os_type=os_type,
                            storage=storage_type_key,
                            vm_index=vm_index,
                            namespace=scale_namespace,
                            client=unprivileged_client,
                        )
                    )
                except TimeoutExpiredError:
                    LOGGER.error(
                        "Could not start new VM, running must-gather, check cluster capacity."
                    )
                    failure_finalizer(
                        vms_list=vms_list, must_gather_image_url=must_gather_image_url
                    )
    for vm in vms_list:
        vm.vmi.wait_until_running()
    yield vms_list


@pytest.mark.polarion("CNV-7713")
def test_scale(
    scale_test_param,
    fail_if_param_vms_zero,
    scale_dvs,
    data_sources,
    scale_namespace,
    vms,
    must_gather_image_url,
):
    log_nodes_load_data(vms=vms)
    LOGGER.info("Verifying all VMS are running")
    try:
        sampler = TimeoutSampler(
            wait_timeout=scale_test_param["test_duration"] * TIMEOUT_1MIN,
            sleep=scale_test_param["vms_verification_interval"] * TIMEOUT_1MIN,
            func=all_vms_running,
            vms=vms,
        )
        for vms_are_ready in sampler:
            if not vms_are_ready:
                LOGGER.error("VMs check failed, running must gather to collect data.")
                failure_finalizer(
                    vms_list=vms, must_gather_image_url=must_gather_image_url
                )
    except TimeoutExpiredError:
        if not scale_test_param["keep_resources"]:
            delete_resources(
                namespace=scale_namespace,
                vms=vms,
                scale_dvs=scale_dvs,
                data_sources=data_sources,
            )
