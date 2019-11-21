# -*- coding: utf-8 -*-

import json
import logging
import re

from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.utils import TimeoutSampler
from rrmngmnt import ssh, user
from utilities import console
from utilities.virt import vm_console_run_commands, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


def vm_started(vm, wait_for_interfaces=True):
    """ Start a VM and wait for its status to be 'Running'

    If wait_for_interfaces - wait for interfaces to be up.
    """

    vm.start(wait=True)
    vm.vmi.wait_until_running()
    if wait_for_interfaces:
        wait_for_vm_interfaces(vm.vmi)


def wait_for_windows_vm(vm, version, winrmcli_pod):
    """
    Samples Windows VM; wait for it to complete the boot process.
    """

    LOGGER.info(
        f"Windows VM {vm.name} booting up, "
        f"will attempt to access it up to 25 minutes."
    )

    vmi_ipaddr = vm.vmi.virt_launcher_pod.instance.status.podIP
    command = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vmi_ipaddr} \
        -username {py_config['windows_username']} -password {py_config['windows_password']} \
        'wmic os get Caption /value'",
    ]

    sampler = TimeoutSampler(
        timeout=1500, sleep=15, func=winrmcli_pod.execute, command=command,
    )
    for sample in sampler:
        if version in str(sample):
            return True


def vm_os_version(vm):
    """ Verify VM os version using console """

    # vm.name format is <os type>-<os major version>-<minor version>
    # For example: rhel-7-6
    # The os version in /etc/redhat-release is formated as <os major version>.<minor version>
    # For example: 7.6
    os = re.search(r"(\w+-)?(\d+(-\d+)?)", vm.name).group(2)
    command = [f"cat /etc/redhat-release | grep {os.replace('-', '.')} | wc -l"]

    vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=command)


def vm_deleted(vm):
    try:
        vm.delete(wait=True)
        return True
    except NotFoundError:
        return False


def check_ssh_connection(ip, port):
    """ Verifies successful SSH connection
    Args:
        ip (str): host IP
        port (int): host port

    Returns:
        bool: True if connection succeeds else False
    """

    LOGGER.info("Check SSH connection to VM.")
    ssh_user = user.User(name=console.RHEL._USERNAME, password=console.RHEL._PASSWORD)
    return ssh.RemoteExecutor(
        user=ssh_user, address=ip, port=port
    ).wait_for_connectivity_state(positive=True, timeout=120)


def check_vm_xml_hyperv(vm):
    """ Verify HyperV values in VMI """

    hyperv_features = vm.vmi.xml_dict["domain"]["features"]["hyperv"]
    assert hyperv_features["relaxed"]["@state"] == "on"
    assert hyperv_features["vapic"]["@state"] == "on"
    assert hyperv_features["spinlocks"]["@state"] == "on"
    assert int(hyperv_features["spinlocks"]["@retries"]) == 8191


def check_windows_vm_hvinfo(vm, winrmcli_pod):
    """ Verify HyperV values in Windows VMI using hvinfo """

    vmi_ipaddr = vm.vmi.virt_launcher_pod.instance.status.podIP
    winrmcli = (
        f"/bin/winrm-cli -username {py_config['windows_username']} "
        f"-password {py_config['windows_password']}"
    )
    run_hvinfo_cmd = [
        "bash",
        "-c",
        f"{winrmcli} -hostname {vmi_ipaddr} C:\\\\hvinfo\\\\hvinfo.exe",
    ]

    hvinfo_dict = json.loads(winrmcli_pod.execute(run_hvinfo_cmd, timeout=20))

    assert hvinfo_dict["HyperVsupport"]
    recommendations = hvinfo_dict["Recommendations"]
    assert recommendations["RelaxedTiming"]
    assert recommendations["MSRAPICRegisters"]
    assert int(recommendations["SpinlockRetries"]) == 8191
