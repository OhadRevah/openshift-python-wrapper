# -*- coding: utf-8 -*-

import json
import logging
import re
import socket

from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources import pod
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from rrmngmnt import ssh, user
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


def stop_start_vm(vm, wait_for_interfaces=True):
    vm.stop(wait=True)
    vm_started(vm, wait_for_interfaces)


def reboot_vm(vm, winrmcli_pod):
    try:
        execute_winrm_cmd(
            vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
            winrmcli_pod=winrmcli_pod,
            cmd="powershell restart-computer -force",
            timeout=60,
        )
    # When a reboot command is executed, a resources.pod.ExecOnPodError exception is raised:
    # "connection reset by peer"
    except pod.ExecOnPodError as e:
        if "connection reset by peer" in e.out:
            pass


def execute_winrm_cmd(vmi_ip, winrmcli_pod, cmd, timeout=20):

    LOGGER.info(f"Running {cmd} via winrm pod.")

    winrmcli_cmd = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vmi_ip} \
        -username {py_config['windows_username']} -password {py_config['windows_password']} \
        '{cmd}'",
    ]

    return winrmcli_pod.execute(winrmcli_cmd, timeout=timeout)


def wait_for_windows_vm(vm, version, winrmcli_pod, timeout=1500):
    """
    Samples Windows VM; wait for it to complete the boot process.
    """

    LOGGER.info(
        f"Windows VM {vm.name} booting up, "
        f"will attempt to access it up to 25 minutes."
    )

    sampler = TimeoutSampler(
        timeout=timeout,
        sleep=15,
        func=execute_winrm_cmd,
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd="wmic os get Caption /value",
    )
    for sample in sampler:
        if version in str(sample):
            return True


def vm_os_version(vm, console_impl):
    """ Verify VM os version using console """

    # vm.name format is <os type>-<os major version>-<minor version>
    # For example: rhel-7-6
    # The os version in /etc/redhat-release is formated as <os major version>.<minor version>
    # For example: 7.6
    os = re.search(r"(\w+-)?(\d+(-\d+)?)", vm.name).group(2)
    command = [f"cat /etc/redhat-release | grep {os.replace('-', '.')} | wc -l"]

    vm_console_run_commands(console_impl=console_impl, vm=vm, commands=command)


def vm_deleted(vm):
    try:
        vm.delete(wait=True)
        return True
    except NotFoundError:
        return False


def wait_for_console(vm, console_impl):
    with console_impl(vm=vm, timeout=1500):
        pass


def check_ssh_connection(ip, port, console_impl):
    """ Verifies successful SSH connection
    Args:
        ip (str): host IP
        port (int): host port

    Returns:
        bool: True if connection succeeds else False
    """

    LOGGER.info("Check SSH connection to VM.")
    ssh_user = user.User(name=console_impl._USERNAME, password=console_impl._PASSWORD,)
    return ssh.RemoteExecutor(
        user=ssh_user, address=ip, port=port
    ).wait_for_connectivity_state(positive=True, timeout=120)


def check_telnet_connection(ip, port):
    """ Verifies successful telnet connection
    Args:
        ip (str): host IP
        port (int): host port

    Returns:
        bool: True if connection succeeds else False
    """

    LOGGER.info("Check telnet connection to VM.")
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s1.connect((ip, int(port)))
        s1.close()
        return True
    except ConnectionRefusedError:
        return False


def migrate_vm(vm):
    with VirtualMachineInstanceMigration(
        name=vm.name, namespace=vm.namespace, vmi=vm.vmi,
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=1500)


def check_vm_xml_hyperv(vm):
    """ Verify HyperV values in VMI """

    hyperv_features = vm.vmi.xml_dict["domain"]["features"]["hyperv"]
    assert hyperv_features["relaxed"]["@state"] == "on"
    assert hyperv_features["vapic"]["@state"] == "on"
    assert hyperv_features["spinlocks"]["@state"] == "on"
    assert int(hyperv_features["spinlocks"]["@retries"]) == 8191


def check_windows_vm_hvinfo(vm, winrmcli_pod):
    """ Verify HyperV values in Windows VMI using hvinfo """

    hvinfo_dict = json.loads(
        execute_winrm_cmd(
            vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
            winrmcli_pod=winrmcli_pod,
            cmd="C:\\\\hvinfo\\\\hvinfo.exe",
            timeout=90,
        )
    )

    assert hvinfo_dict["HyperVsupport"]
    recommendations = hvinfo_dict["Recommendations"]
    assert recommendations["RelaxedTiming"]
    assert recommendations["MSRAPICRegisters"]
    assert int(recommendations["SpinlockRetries"]) == 8191


def add_windows_license(vm, winrmcli_pod, windows_license):

    LOGGER.info("Add Windows license.")
    addition_status = execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd=f"cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /ipk {windows_license}",
        timeout=90,
    )
    assert re.match(
        r"Installed product key [a-z0-9-]+ successfully.",
        addition_status,
        re.IGNORECASE,
    ), "Failed to add license."


def activate_windows_online(vm, winrmcli_pod):

    LOGGER.info("Activate Windows license online.")
    online_activation_status = execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd="cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /ato",
        timeout=240,
    )
    assert re.match(
        r"Activating Windows\(R\), (ServerStandard|Professional) edition "
        r"\(.*\) \.+.*Product activated successfully",
        online_activation_status,
        re.DOTALL,
    ), "Failed to activate Windows online."


def is_windows_activated(vm, winrmcli_pod):
    """ Returns True if license is active else False """

    return "The machine is permanently activated" in execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd="cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /xpr",
    )


def check_windows_activated_license(vm, winrmcli_pod, reset_action):
    """ Verify VM activation mode after VM reset (reboot / stop and start) """

    if "stop_start" in reset_action:
        stop_start_vm(vm=vm, wait_for_interfaces=False)
    if "reboot" in reset_action:
        reboot_vm(vm, winrmcli_pod)
    wait_for_windows_vm(
        vm=vm, version=vm.name.split("-")[-1], winrmcli_pod=winrmcli_pod
    )
    assert is_windows_activated(
        vm, winrmcli_pod
    ), "VM license is not activated after restart."
