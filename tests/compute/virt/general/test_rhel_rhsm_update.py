# -*- coding: utf-8 -*-

"""
RHSM account was created using http://account-manager-stage.app.eng.rdu2.redhat.com/#create
Username: cnv-qe-auto-stage, password:
Account subscriptions: qum5net
ESA0001 - Red Hat Enterprise Linux, Premium
RH00076 - Red Hat Enterprise Linux High Touch Beta
"""

import base64
import logging

import pytest
from pytest_testconfig import config as py_config
from resources.secret import Secret

from tests.compute.utils import remove_eth0_default_gw
from tests.conftest import vm_instance_from_template
from utilities import console
from utilities.virt import RHEL_CLOUD_INIT_PASSWORD, vm_console_run_commands


LOGGER = logging.getLogger(__name__)
DISK_SERIAL = "D23YZ9W6WA5DJ489"
SECRET_NAME = "rhsm-secret"


def base64_encode_str(text):
    return base64.b64encode(text.encode()).decode()


@pytest.fixture()
def rhsm_created_secret(namespace):
    with Secret(
        name=SECRET_NAME,
        namespace=namespace.name,
        data_dict={
            "username": base64_encode_str(text="cnv-qe-auto-stage"),
            "password": base64_encode_str(text="qum5net"),
        },
    ) as secret:
        yield secret


@pytest.fixture()
def rhsm_cloud_init_data():
    bootcmds = [
        f"mkdir /mnt/{SECRET_NAME}",
        f'mount /dev/$(lsblk --nodeps -no name,serial | grep {DISK_SERIAL} | cut -f1 -d" ") /mnt/{SECRET_NAME}',
        "subscription-manager config --rhsm.auto_enable_yum_plugins=0",
    ]

    rhsm_cloud_init_data = RHEL_CLOUD_INIT_PASSWORD
    rhsm_cloud_init_data["userData"]["bootcmd"] = bootcmds

    return rhsm_cloud_init_data


@pytest.fixture()
def rhsm_vm(
    request,
    unprivileged_client,
    rhel7_workers,
    namespace,
    golden_image_data_volume_scope_function,
    network_configuration,
    rhsm_cloud_init_data,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=rhsm_cloud_init_data,
    ) as rhsm_vm:
        if rhel7_workers:
            remove_eth0_default_gw(vm=rhsm_vm, console_impl=console.RHEL)
        yield rhsm_vm


@pytest.fixture()
def registered_rhsm(rhsm_vm):
    LOGGER.info("Register the VM with RedHat Subscription Manager")

    vm_console_run_commands(
        console_impl=console.RHEL,
        vm=rhsm_vm,
        commands=[
            "sudo subscription-manager register "
            "--serverurl=subscription.rhsm.stage.redhat.com:443/subscription "
            "--baseurl=https://cdn.stage.redhat.com "
            f"--username=`sudo cat /mnt/{SECRET_NAME}/username` "
            f"--password=`sudo cat /mnt/{SECRET_NAME}/password` "
            "--auto-attach"
        ],
        timeout=180,
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, rhsm_vm",
    [
        pytest.param(
            {
                "dv_name": py_config["latest_rhel_version"]["template_labels"]["os"],
                "image": py_config["latest_rhel_version"]["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
            {
                "vm_name": "rhel-rhsm-vm",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "attached_secret": {
                    "volume_name": "rhsm-secret-vol",
                    "serial": DISK_SERIAL,
                    "secret_name": SECRET_NAME,
                },
            },
            marks=pytest.mark.polarion("CNV-4006"),
        ),
    ],
    indirect=True,
)
def test_rhel_yum_update(
    skip_upstream,
    unprivileged_client,
    namespace,
    rhsm_created_secret,
    golden_image_data_volume_scope_function,
    rhsm_vm,
    registered_rhsm,
):
    vm_console_run_commands(
        console_impl=console.RHEL,
        vm=rhsm_vm,
        commands=["sudo yum update -y curl"],
        timeout=180,
    )