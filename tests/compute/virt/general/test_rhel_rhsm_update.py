# -*- coding: utf-8 -*-

"""
RHSM account was created using http://account-manager-stage.app.eng.rdu2.redhat.com/#create
Username: cnv-qe-auto-stage, password:
Account subscriptions: qum5net
ESA0001 - Red Hat Enterprise Linux, Premium
RH00076 - Red Hat Enterprise Linux High Touch Beta
"""

import logging
import shlex

import pytest
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import RHSM_PASSWD, RHSM_USER
from utilities.infra import base64_encode_str, run_ssh_commands
from utilities.virt import prepare_cloud_init_user_data, vm_instance_from_template


LOGGER = logging.getLogger(__name__)
DISK_SERIAL = "D23YZ9W6WA5DJ489"
SECRET_NAME = "rhsm-secret"


@pytest.fixture()
def rhsm_created_secret(namespace):
    with Secret(
        name=SECRET_NAME,
        namespace=namespace.name,
        data_dict={
            "username": base64_encode_str(text=RHSM_USER),
            "password": base64_encode_str(text=RHSM_PASSWD),
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

    return prepare_cloud_init_user_data(section="bootcmd", data=bootcmds)


@pytest.fixture()
def rhsm_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
    rhsm_cloud_init_data,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
        cloud_init_data=rhsm_cloud_init_data,
    ) as rhsm_vm:
        yield rhsm_vm


@pytest.fixture()
def registered_rhsm(rhsm_vm):
    LOGGER.info("Register the VM with RedHat Subscription Manager")

    run_ssh_commands(
        host=rhsm_vm.ssh_exec,
        commands=shlex.split(
            "sudo subscription-manager register "
            "--serverurl=subscription.rhsm.stage.redhat.com:443/subscription "
            "--baseurl=https://cdn.stage.redhat.com "
            f"--username=`sudo cat /mnt/{SECRET_NAME}/username` "
            f"--password=`sudo cat /mnt/{SECRET_NAME}/password` "
            "--auto-attach"
        ),
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, rhsm_vm",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel-rhsm-vm",
                "template_labels": RHEL_LATEST_LABELS,
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
    run_ssh_commands(
        host=rhsm_vm.ssh_exec,
        commands=shlex.split("sudo yum update -y curl"),
    )
