import datetime
import logging
import os
import re
import shlex
from collections import Counter

import pytest
import yaml
from kubernetes.dynamic.exceptions import ForbiddenError
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
from utilities.infra import (
    create_must_gather_command,
    create_ns,
    run_cnv_must_gather,
    run_command,
)
from utilities.storage import generate_data_source_dict, get_images_server_url
from utilities.virt import VirtualMachineForTestsFromTemplate


LOGGER = logging.getLogger(__name__)
OCS = "ocs"
NFS = "nfs"
TESTS_CLASS_NAME = "TestScale"

SCALE_STORAGE_TYPES = {
    OCS: StorageClass.Types.CEPH_RBD,
    NFS: StorageClass.Types.NFS,
}
pytestmark = pytest.mark.scale


def log_nodes_load_data(vms=None):
    """
    Log the distribution of VM's on the nodes, and the cluster memory/cpu statistics

    Args:
        vms (list): List of vms to log statistics on
    """
    nodes_load_distribute = Counter([vm.vmi.node.name for vm in vms or []])
    LOGGER.info(
        f"Nodes vm load distribution: {nodes_load_distribute or 'no scale VMs running'}"
    )
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
    num_of_running_vms = len([vm for vm in vms if vm.vmi.status == vm.Status.RUNNING])
    LOGGER.info(f"Number of running vms: {num_of_running_vms}")
    return num_of_running_vms == len(vms)


def delete_resources(resources):
    deleted_resources = []
    for _resource in resources:
        try:
            _resource.delete()
            deleted_resources.append(_resource)
        except ForbiddenError:
            pass
    for _resource in deleted_resources:
        _resource.wait_deleted()


def save_must_gather_logs(must_gather_image_url):
    logs_path = os.path.join(
        os.path.expanduser("~"),
        f"must_gather_{datetime.datetime.utcnow().strftime('%Y_%m_%d_%H_%M_%S')}",
    )
    os.makedirs(logs_path)
    must_gather_command = create_must_gather_command(
        image_url=must_gather_image_url, dest_dir=logs_path
    )
    return run_cnv_must_gather(must_gather_cmd=must_gather_command)


def failure_finalizer(vms_list, must_gather_image_url):
    log_nodes_load_data(vms=vms_list)
    logs_folders = save_must_gather_logs(must_gather_image_url=must_gather_image_url)
    pytest.fail(
        msg=f"Test failed, keeping the test environment. the must-gather logs are saved under {logs_folders}"
    )


@pytest.fixture(scope="class")
def fail_if_param_vms_zero(expected_num_of_vms):
    if expected_num_of_vms == 0:
        pytest.fail(
            f"The sum of the VMs number in the scale_params.yaml file is {expected_num_of_vms}"
        )


@pytest.fixture(scope="class")
def keep_resources(scale_test_param):
    return scale_test_param["keep_resources"]


@pytest.fixture()
def skip_if_keep_resources(keep_resources):
    if keep_resources:
        pytest.skip(
            f"Skipping scale test resources deletion, keep_resources parameter = {keep_resources}"
        )


@pytest.fixture(scope="class")
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


@pytest.fixture(scope="class")
def scale_test_param(pytestconfig):
    with open(pytestconfig.option.scale_params_file) as params_file:
        return yaml.safe_load(stream=params_file)


@pytest.fixture(scope="class")
def scale_namespace(unprivileged_client, scale_test_param, keep_resources):
    yield from create_ns(
        name=scale_test_param["test_namespace"],
        teardown=not keep_resources,
        unprivileged_client=unprivileged_client,
    )


@pytest.fixture(scope="class")
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


@pytest.fixture(scope="class")
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


@pytest.fixture(scope="class")
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
        vms_info_dict[os_name]["run_strategy"] = scale_test_param["vms"][os_name][
            "run_strategy"
        ]
    return vms_info_dict


@pytest.fixture(scope="class")
def golden_images_scale_dvs(
    request, keep_resources, admin_client, golden_images_namespace, dvs_info
):
    dvs_list = []

    def _delete_resources():
        delete_resources(resources=dvs_list)

    if not keep_resources:
        request.addfinalizer(_delete_resources)

    for os_name, dv_info in dvs_info.items():
        storage_types_used = [
            storage_type_key
            for storage_type_key in SCALE_STORAGE_TYPES
            if dv_info[storage_type_key]["vms"]
        ]
        for storage_type in storage_types_used:
            golden_images_scale_dv = DataVolume(
                name=f"{os_name}-{storage_type}-dv",
                namespace=golden_images_namespace.name,
                storage_class=SCALE_STORAGE_TYPES[storage_type],
                api_name="storage",
                url=f"{get_images_server_url(schema='http')}{dv_info['url']}",
                size=dv_info["size"],
                client=admin_client,
                source="http",
            )
            golden_images_scale_dv.deploy()
            dvs_list.append(golden_images_scale_dv)
    for dv in dvs_list:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=TIMEOUT_30MIN)
    return dvs_list


@pytest.fixture(scope="class")
def data_sources(request, keep_resources, admin_client, golden_images_scale_dvs):
    data_sources = {}

    def _delete_resources():
        delete_resources(resources=list(data_sources.values()))

    if not keep_resources:
        request.addfinalizer(_delete_resources)

    for dv in golden_images_scale_dvs:
        data_source_name = re.sub(r"-dv$", r"-datasource", dv.name)
        data_source = DataSource(
            name=data_source_name,
            namespace=dv.namespace,
            client=admin_client,
            source=generate_data_source_dict(dv=dv),
        )
        data_source.deploy()
        data_sources.update({data_source.name: data_source})
    for data_source in data_sources.values():
        data_source.wait_for_condition(
            condition=data_source.Condition.READY,
            status=data_source.Condition.Status.TRUE,
        )
    return data_sources


@pytest.fixture(scope="class")
def scale_vms(
    unprivileged_client,
    data_sources,
    scale_namespace,
    vms_info,
):
    vms_list = []

    for os_type, vm_info in vms_info.items():
        for storage_type_key in SCALE_STORAGE_TYPES:
            vm_base_name = f"{os_type}-{storage_type_key}"
            num_of_vms = vm_info[storage_type_key]["vms"]
            for vm_index in range(num_of_vms):
                vms_list.append(
                    VirtualMachineForTestsFromTemplate(
                        name=f"vm-{vm_base_name}-{vm_index}",
                        namespace=scale_namespace.name,
                        client=unprivileged_client,
                        cpu_cores=vm_info["cores"],
                        memory_requests=vm_info["memory"],
                        data_source=data_sources[f"{vm_base_name}-datasource"],
                        labels=Template.generate_template_labels(
                            **vm_info["latest_labels"]
                        ),
                        run_strategy=vm_info["run_strategy"],
                    )
                )
    yield vms_list


class TestScale:
    # TODO add timer for tests to check for time of creation
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_create_vms")
    @pytest.mark.polarion("CNV-8447")
    def test_create_vms(
        self,
        fail_if_param_vms_zero,
        scale_vms,
    ):
        log_nodes_load_data()
        for vm in scale_vms:
            vm.deploy()

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_start_vms",
        depends=[f"{TESTS_CLASS_NAME}::test_create_vms"],
    )
    @pytest.mark.polarion("CNV-8448")
    def test_start_vms(self, scale_vms, must_gather_image_url):
        for vm in scale_vms:
            if vm.instance.spec.runStrategy == vm.RunStrategy.ALWAYS:
                continue
            vm.start()
        for vm in scale_vms:
            try:
                vm.vmi.wait(timeout=TIMEOUT_30MIN)
                vm.vmi.wait_until_running()
            except TimeoutExpiredError:
                LOGGER.error(
                    "Could not start new VM, running must-gather, check cluster capacity."
                )
                failure_finalizer(
                    vms_list=scale_vms, must_gather_image_url=must_gather_image_url
                )

    # TODO check the os internally to see if it didn't reboot
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_start_vms"])
    @pytest.mark.polarion("CNV-8449")
    def test_scale_vms_running_stability(
        self,
        scale_test_param,
        scale_vms,
        must_gather_image_url,
    ):
        log_nodes_load_data(vms=scale_vms)
        LOGGER.info("Verifying all VMS are running")
        try:
            sampler = TimeoutSampler(
                wait_timeout=scale_test_param["test_duration"] * TIMEOUT_1MIN,
                sleep=scale_test_param["vms_verification_interval"] * TIMEOUT_1MIN,
                func=all_vms_running,
                vms=scale_vms,
            )
            for vms_are_ready in sampler:
                if not vms_are_ready:
                    LOGGER.error(
                        "VMs check failed, running must gather to collect data."
                    )
                    failure_finalizer(
                        vms_list=scale_vms, must_gather_image_url=must_gather_image_url
                    )
        except TimeoutExpiredError:
            return

    @pytest.mark.order(after=f"{TESTS_CLASS_NAME}::test_scale_vms_running_stability")
    @pytest.mark.polarion("CNV-8883")
    def test_delete_resources(
        self,
        skip_if_keep_resources,
        golden_images_scale_dvs,
        data_sources,
        scale_namespace,
        scale_vms,
    ):
        # TODO record time for the deletion of VMs and the cloned DVs
        delete_resources(
            resources=list(data_sources.values()) + golden_images_scale_dvs + scale_vms
        )
        scale_namespace.clean_up()
