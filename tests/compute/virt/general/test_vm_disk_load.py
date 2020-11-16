# -*- coding: utf-8 -*-

import logging
import re

import pytest
from pytest_testconfig import config as py_config
from resources.utils import TimeoutSampler
from tests.compute.utils import migrate_vm, rrmngmnt_host
from tests.conftest import vm_instance_from_template
from utilities import console
from utilities.virt import FEDORA_CLOUD_INIT_PASSWORD, enable_ssh_service_in_vm


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_cloud_init_data():
    rhsm_cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    rhsm_cloud_init_data["userData"]["bootcmd"] = ["yum -y install fio iotop"]

    return rhsm_cloud_init_data


@pytest.fixture()
def vm_with_fio(
    request,
    unprivileged_client,
    nodes_common_cpu_model,
    namespace,
    data_volume_scope_function,
    vm_cloud_init_data,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_scope_function,
        cloud_init_data=vm_cloud_init_data,
        vm_cpu_model=nodes_common_cpu_model,
    ) as vm_with_fio:
        enable_ssh_service_in_vm(vm=vm_with_fio, console_impl=console.Fedora)
        yield vm_with_fio


@pytest.fixture()
def vm_rrmngmnt_host(schedulable_node_ips, vm_with_fio):
    return rrmngmnt_host(
        usr=console.Fedora.USERNAME,
        passwd=console.Fedora.PASSWORD,
        ip=vm_with_fio.ssh_service.service_ip,
        port=vm_with_fio.ssh_service.service_port,
    )


@pytest.fixture()
def run_fio_in_vm(vm_rrmngmnt_host):
    # Random write/read -  create a 1G file, and perform 4KB reads and writes using a 75%/25%
    LOGGER.info("Running fio in VM")
    fio_cmd = [
        "sudo",
        "nohup",
        "bash",
        "-c",
        "/usr/bin/fio --loops=200 --runtime=600 --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 "
        "--name=test --filename=/home/fedora/random_read_write.fio --bs=4k --iodepth=64 --size=1G --readwrite=randrw "
        "--rwmixread=75 --numjobs=8 >& /dev/null &",
        "&",
    ]
    vm_rrmngmnt_host.run_command(command=fio_cmd)


def get_disk_usage(vm_rrmngmnt_host):
    def _wait_for_iotop_output():
        # After migration, the SSH connection may not be accessible for a brief moment ("No route to host")
        for sample in TimeoutSampler(
            timeout=60,
            sleep=5,
            func=vm_rrmngmnt_host.run_command,
            command="sudo iotop -b -n 1 -o".split(),
            tcp_timeout=60,
        ):
            if sample:
                return sample

    iotop_output = _wait_for_iotop_output()
    LOGGER.info(f"iotop output: {iotop_output}")
    # Example output for regex: 'Actual DISK READ:       3.00 M/s | Actual DISK WRITE:    1303.72 '
    iotop_read_write_str = re.search(r"Actual DISK READ: .* ", iotop_output[1]).group(0)
    # Example value of read_write_values : ('3.00', '3.72')
    read_write_values = re.search(
        r"READ:.*(\d+\.\d+) .*WRITE:.*(\d+\.\d+)", iotop_read_write_str
    ).groups()
    assert not any(
        [disk_io for disk_io in read_write_values if disk_io == "0.00"]
    ), "No load on disks"


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_with_fio",
    [
        pytest.param(
            {
                "dv_name": "dv-fedora-load-vm",
                "image": py_config["latest_fedora_version"]["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
            },
            {
                "vm_name": "fedora-load-vm",
                "template_labels": py_config["latest_fedora_version"][
                    "template_labels"
                ],
                "cpu_threads": 2,
                "ssh": True,
            },
            marks=pytest.mark.polarion("CNV-4663"),
        ),
    ],
    indirect=True,
)
def test_fedora_vm_load_migration(
    skip_upstream,
    skip_rhel7_workers,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    vm_cloud_init_data,
    vm_with_fio,
    run_fio_in_vm,
    vm_rrmngmnt_host,
):
    LOGGER.info("Test migrate VM with disk load")
    migrate_vm(vm=vm_with_fio)
    get_disk_usage(vm_rrmngmnt_host=vm_rrmngmnt_host)
