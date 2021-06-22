# -*- coding: utf-8 -*-

import logging
import re
import shlex

import pytest
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutSampler

from tests.conftest import vm_instance_from_template
from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS, FEDORA_LATEST_OS
from utilities.infra import run_ssh_commands
from utilities.virt import migrate_vm_and_verify, running_vm


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures("skip_test_if_no_ocs_sc")


@pytest.fixture()
def vm_with_fio(
    request,
    unprivileged_client,
    nodes_common_cpu_model,
    namespace,
    golden_image_data_volume_scope_function,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_function,
        vm_cpu_model=nodes_common_cpu_model,
    ) as vm_with_fio:
        running_vm(vm=vm_with_fio)
        yield vm_with_fio


@pytest.fixture()
def run_fio_in_vm(vm_with_fio):
    # Random write/read -  create a 1G file, and perform 4KB reads and writes using a 75%/25%
    LOGGER.info("Running fio in VM")
    fio_cmd = [
        "sudo",
        "nohup",
        "bash",
        "-c",
        "/usr/bin/fio --loops=400 --runtime=600 --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 "
        "--name=test --filename=/home/fedora/random_read_write.fio --bs=4k --iodepth=64 --size=1G --readwrite=randrw "
        "--rwmixread=75 --numjobs=8 >& /dev/null &",
        "&",
    ]
    run_ssh_commands(host=vm_with_fio.ssh_exec, commands=fio_cmd)


def get_disk_usage(ssh_exec):
    def _wait_for_iotop_output():
        # After migration, the SSH connection may not be accessible for a brief moment ("No route to host")
        for sample in TimeoutSampler(
            wait_timeout=60,
            sleep=5,
            func=run_ssh_commands,
            host=ssh_exec,
            commands=shlex.split("sudo iotop -b -n 1 -o"),
        ):
            if sample:
                return sample

    iotop_output = _wait_for_iotop_output()
    LOGGER.info(f"iotop output: {iotop_output}")
    # Example output for regex: 'Actual DISK READ:       3.00 M/s | Actual DISK WRITE:    1303.72 '
    iotop_read_write_str = re.search(r"Actual DISK READ: .* ", iotop_output[0]).group(0)
    # Example value of read_write_values : ('3.00', '3.72')
    read_write_values = re.search(
        r"READ:.*(\d+\.\d+) .*WRITE:.*(\d+\.\d+)", iotop_read_write_str
    ).groups()
    assert not any(
        [disk_io for disk_io in read_write_values if disk_io == "0.00"]
    ), "No load on disks"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_with_fio",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST["image_path"],
                "storage_class": StorageClass.Types.CEPH_RBD,
                "dv_size": FEDORA_LATEST["dv_size"],
            },
            {
                "vm_name": "fedora-load-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "cpu_threads": 2,
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
    golden_image_data_volume_scope_function,
    vm_with_fio,
    run_fio_in_vm,
):
    LOGGER.info("Test migrate VM with disk load")
    migrate_vm_and_verify(vm=vm_with_fio, check_ssh_connectivity=True)
    get_disk_usage(ssh_exec=vm_with_fio.ssh_exec)
