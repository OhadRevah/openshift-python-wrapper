# -*- coding: utf-8 -*-

import json
import logging
import re
import socket
import tarfile
import urllib.request
import xml.etree.ElementTree as EleTree

import bitmath
import tests.network.utils as network_utils
from openshift.dynamic.exceptions import NotFoundError
from resources import pod
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from rrmngmnt import ssh, user
from tests.compute.utils import execute_ssh_command, execute_winrm_cmd, vm_started
from utilities.virt import vm_console_run_commands


LOGGER = logging.getLogger(__name__)


def stop_start_vm(vm, wait_for_interfaces=True):
    vm.stop(wait=True)
    vm_started(vm, wait_for_interfaces)


def reboot_vm(vm, winrmcli_pod, helper_vm=False):
    try:
        execute_winrm_cmd(
            vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
            winrmcli_pod=winrmcli_pod,
            cmd="powershell restart-computer -force",
            target_vm=vm,
            helper_vm=helper_vm,
            timeout=60,
        )
    # When a reboot command is executed, a resources.pod.ExecOnPodError exception is raised:
    # "connection reset by peer"
    except pod.ExecOnPodError as e:
        if "connection reset by peer" in e.out:
            pass


def wait_for_windows_vm(vm, version, winrmcli_pod, timeout=1500, helper_vm=False):
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
        target_vm=vm,
        helper_vm=helper_vm,
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


def get_vm_accessible_ip(rhel7_workers, schedulable_node_ips, vm):
    return (
        network_utils.get_vmi_ip_v4_by_name(vmi=vm.vmi, name=[*vm.networks][0])
        if rhel7_workers
        else list(schedulable_node_ips.values())[0]
    )


def get_vm_ssh_port(rhel7_workers, vm):
    return 22 if rhel7_workers else vm.ssh_node_port


def check_ssh_connection(ip, port, console_impl):
    """ Verifies successful SSH connection
    Args:
        ip (str): host IP
        port (int): host port

    Returns:
        bool: True if connection succeeds else False
    """

    LOGGER.info("Check SSH connection to VM.")

    ssh_user = user.User(name=console_impl.USERNAME, password=console_impl.PASSWORD,)
    return ssh.RemoteExecutor(
        user=ssh_user, address=str(ip), port=port
    ).wait_for_connectivity_state(
        positive=True, timeout=120, tcp_connection_timeout=120,
    )


def check_telnet_connection(ip, port):
    """ Verifies successful telnet connection
    Args:
        ip (str): host IP
        port (int): host port

    Returns:
        bool: True if connection succeeds else False
    """

    LOGGER.info("Check telnet connection to VM.")
    sampler = TimeoutSampler(
        timeout=120,
        sleep=15,
        exceptions=ConnectionRefusedError,
        func=socket.create_connection,
        address=(ip, int(port)),
    )
    for sample in sampler:
        if sample:
            sample.close()
            return True


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
    # The below entries do not appear in Windows hyperV
    if "Windows" not in vm.vmi.instance.status.guestOSInfo.name:
        assert hyperv_features["stimer"]["@state"] == "on"
        assert hyperv_features["vpindex"]["@state"] == "on"
        assert hyperv_features["synic"]["@state"] == "on"


def check_vm_xml_clock(vm):
    """ Verify clock values in VMI """

    clock_timer_list = vm.vmi.xml_dict["domain"]["clock"]["timer"]
    assert [i for i in clock_timer_list if i["@name"] == "hpet"][0]["@present"] == "no"
    assert [i for i in clock_timer_list if i["@name"] == "hypervclock"][0][
        "@present"
    ] == "yes"


def check_windows_vm_hvinfo(vm, winrmcli_pod, helper_vm=False):
    """ Verify HyperV values in Windows VMI using hvinfo """

    hvinfo_dict = None

    sampler = TimeoutSampler(
        timeout=90,
        sleep=15,
        func=execute_winrm_cmd,
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        target_vm=vm,
        helper_vm=helper_vm,
        cmd="C:\\\\hvinfo\\\\hvinfo.exe",
    )
    for sample in sampler:
        if sample and "connect: connection refused" not in sample:
            hvinfo_dict = json.loads(sample)
            break

    assert hvinfo_dict["HyperVsupport"]
    recommendations = hvinfo_dict["Recommendations"]
    assert recommendations["RelaxedTiming"]
    assert recommendations["MSRAPICRegisters"]
    assert int(recommendations["SpinlockRetries"]) == 8191


def set_vm_tablet_device_dict(tablet_params):
    """  Generates VM tablet device dict """

    return {
        "spec": {
            "template": {"spec": {"domain": {"devices": {"inputs": [tablet_params]}}}}
        }
    }


def check_vm_system_tablet_device(vm, console_impl, expected_device):
    """ Verify tablet device parameters in VMI /sys/devices file """

    with console_impl(vm=vm, timeout=1500) as vm_console:
        vm_console.sendline(r"grep -rs '^QEMU *.* Tablet' /sys/devices ")
        vm_console.expect(
            f"/sys/devices/pci(.*)QEMU {expected_device} Tablet", timeout=240
        )


def check_vm_xml_tablet_device(vm):
    """ Verifies vm tablet device info in VM XML vs VM instance attributes
    values.
    """

    LOGGER.info("Verify VM XML - tablet device values.")

    vm_instance_tablet_device_dict = vm.instance["spec"]["template"]["spec"]["domain"][
        "devices"
    ]["inputs"][0]

    tablet_dict_from_xml = [
        i
        for i in vm.vmi.xml_dict["domain"]["devices"]["input"]
        if i["@type"] == "tablet"
    ][0]

    assert (
        tablet_dict_from_xml["@type"] == vm_instance_tablet_device_dict["type"]
    ), "Wrong device type"

    # Default bus type is usb; not added to the VM instance if it was not
    # specified during VM creation.
    assert tablet_dict_from_xml["@bus"] == vm_instance_tablet_device_dict.get(
        "bus", "usb"
    ), "Wrong bus type"
    assert (
        tablet_dict_from_xml["alias"]["@name"]
        == f"ua-{vm_instance_tablet_device_dict['name']}"
    ), "Wrong device name"


def add_windows_license(vm, winrmcli_pod, windows_license, helper_vm=False):
    LOGGER.info("Add Windows license.")
    addition_status = execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd=f"cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /ipk {windows_license}",
        target_vm=vm,
        helper_vm=helper_vm,
        timeout=90,
    )
    assert re.match(
        r"Installed product key [a-z0-9-]+ successfully.",
        addition_status,
        re.IGNORECASE,
    ), "Failed to add license."


def activate_windows_online(vm, winrmcli_pod, helper_vm=False):
    LOGGER.info("Activate Windows license online.")
    online_activation_status = execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd="cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /ato",
        target_vm=vm,
        helper_vm=helper_vm,
        timeout=240,
    )
    assert re.match(
        r"Activating Windows\(R\), (ServerStandard|Professional) edition "
        r"\(.*\) \.+.*Product activated successfully",
        online_activation_status,
        re.DOTALL,
    ), "Failed to activate Windows online."


def is_windows_activated(vm, winrmcli_pod, helper_vm=False):
    """ Returns True if license is active else False """

    return "The machine is permanently activated" in execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd="cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /xpr",
        target_vm=vm,
        helper_vm=helper_vm,
    )


def start_and_fetch_processid_on_windows_vm(
    vm, winrmcli_pod, process_name=None, helper_vm=False
):
    """ Start a process and fetch processid from the Windows VM """

    execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd=f"wmic process call create {process_name}",
        target_vm=vm,
        helper_vm=helper_vm,
    )
    return fetch_processid_from_windows_vm(
        vm, winrmcli_pod, process_name=process_name, helper_vm=helper_vm
    )


def fetch_processid_from_windows_vm(
    vm, winrmcli_pod, process_name=None, helper_vm=False
):
    """ Fetch the processid from the Windows VM  """

    return execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd=f"wmic process where (Name='{process_name}') get processid /value",
        target_vm=vm,
        helper_vm=helper_vm,
    )


def check_windows_activated_license(vm, winrmcli_pod, reset_action, helper_vm=False):
    """ Verify VM activation mode after VM reset (reboot / stop and start) """

    if "stop_start" in reset_action:
        stop_start_vm(vm=vm, wait_for_interfaces=False)
    if "reboot" in reset_action:
        reboot_vm(vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm)
    wait_for_windows_vm(
        vm=vm,
        version=vm.name.split("-")[-1],
        winrmcli_pod=winrmcli_pod,
        helper_vm=helper_vm,
    )
    assert is_windows_activated(
        vm, winrmcli_pod, helper_vm
    ), "VM license is not activated after restart."


def add_activate_windows_license(vm, winrm_pod, license_key, helper_vm=False):
    """ Add Windows license to the VM, activate it online and verify that
    the activation was successful.
    """

    add_windows_license(vm, winrm_pod, windows_license=license_key, helper_vm=helper_vm)
    activate_windows_online(
        vm, winrm_pod, helper_vm,
    )
    assert is_windows_activated(vm=vm, winrmcli_pod=winrm_pod, helper_vm=helper_vm), (
        "VM license is not " "activated."
    )


def fetch_osinfo_memory(osinfo_file_path, memory_test, resources_arch):
    """ Fetch memory min and max values from the osinfo files. """

    xml_doc = EleTree.parse(osinfo_file_path)
    root = xml_doc.getroot()
    resources = root.findall("./os/resources")
    return [
        int(resource.findtext(f"./{memory_test}/ram"))
        for resource in resources
        if resources_arch == resource.attrib["arch"]
    ]


def validate_memory(memory_test, template_memory_value, osinfo_memory_value):
    """ Validate the minimum and maximum memory values."""
    if memory_test == "minimum":
        return bitmath.parse_string_unsafe(template_memory_value) >= bitmath.Byte(
            osinfo_memory_value
        )
    elif memory_test == "maximum":
        return bitmath.parse_string_unsafe(template_memory_value) < bitmath.Byte(
            osinfo_memory_value
        )


def download_and_extract_tar(tarfile_url):
    """ Download and Extract the tar file. """

    tar_data = urllib.request.urlopen(tarfile_url)
    thetarfile = tarfile.open(fileobj=tar_data, mode="r|xz")
    thetarfile.extractall()


def check_default_and_validation_memory(
    get_base_templates, osinfo_memory_value, os_type, memory_test, osinfo_filename
):
    for template in [
        template for template in get_base_templates if os_type in template.name
    ]:
        LOGGER.info(
            f"Currently validating template {template.name} against osinfo file {osinfo_filename}.xml"
        )
        requests_memory_value = template.instance.objects[
            0
        ].spec.template.spec.domain.resources.requests.memory

        validation_map = json.loads(template.instance.metadata.annotations.validations)
        min_validation_memory_value = validation_map[0]["min"]

        LOGGER.info(
            f"Checking default requests.memory value against osinfo file {osinfo_filename}.xml"
        )
        assert validate_memory(
            memory_test, requests_memory_value, osinfo_memory_value[0]
        )

        LOGGER.info(
            f"Checking validations minimal-required-memory value against osinfo file {osinfo_filename}.xml"
        )
        assert validate_memory(
            memory_test, min_validation_memory_value, osinfo_memory_value[0]
        )


def os_info_parser(os_info_list, field_name):
    return "".join(
        [x.split("=")[1] for x in os_info_list if x.startswith(f"{field_name}=")]
    )


def validate_linux_guest_agent_info(vm, ip, ssh_port, username, passwd):
    """ Compare guest OS info from VMI (reported by guest agent) and from OS itself. """
    assert get_guest_os_info_from_vmi(vmi=vm.vmi) == get_linux_os_info_from_ssh(
        ip=ip, port=ssh_port, username=username, passwd=passwd
    )


def validate_windows_guest_agent_info(vm, winrmcli_pod, helper_vm=False):
    """ Compare guest OS info from VMI (reported by guest agent) and from OS itself. """
    windown_os_info_from_rmcli = get_windows_os_info_from_rmcli(
        vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm
    )
    for key, val in get_guest_os_info_from_vmi(vmi=vm.vmi).items():
        if key != "id":
            assert (
                val.split("r")[0]
                if "version" in key
                else val in windown_os_info_from_rmcli
            )


def get_guest_os_info_from_vmi(vmi):
    """ Gets guest OS info from VMI. """
    guest_os_info_dict = dict(vmi.instance.status.guestOSInfo)
    assert guest_os_info_dict, "Guest agent not installed/active."
    return guest_os_info_dict


def get_linux_os_info_from_ssh(ip, port, username, passwd):
    """
    Gets Linux OS info via SSH from etc/os-release and uname -r -v.
    Return dict (should be same format as dict from "get_guest_os_info_from_vmi") keys:
    'id', 'kernelRelease', 'kernelVersion', 'name', 'prettyName', 'version', 'versionId'
    """
    os_release_output_list = (
        execute_ssh_command(
            username=username,
            passwd=passwd,
            ip=ip,
            port=port,
            cmd=["cat", "/etc/os-release"],
        )
        .replace('"', "")
        .split("\n")
    )
    kernel_info_output_list = execute_ssh_command(
        username=username,
        passwd=passwd,
        ip=ip,
        port=port,
        cmd=["uname", "-r", ";", "uname", "-v"],
    ).split("\n")

    return {
        "id": os_info_parser(os_release_output_list, "ID"),
        "kernelRelease": kernel_info_output_list[0],
        "kernelVersion": kernel_info_output_list[1],
        "name": os_info_parser(os_release_output_list, "NAME"),
        "prettyName": os_info_parser(os_release_output_list, "PRETTY_NAME"),
        "version": os_info_parser(os_release_output_list, "VERSION").split(" ")[0],
        "versionId": os_info_parser(os_release_output_list, "VERSION_ID"),
    }


def get_windows_os_info_from_rmcli(vm, winrmcli_pod, helper_vm=False):
    """
    Gets Windows OS info via remote cli tool from systeminfo.
    Return string of OS Name and OS Version output of systeminfo.
    """
    return execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd='systeminfo | findstr /B /C:"OS Name" /C:"OS Version"',
        target_vm=vm,
        helper_vm=helper_vm,
    )


def check_machine_type(vm):
    """ VM and VMI should have machine type; machine type cannot be empty """

    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert (
        vm_machine_type == vmi_machine_type
    ), f"VM and VMI machine type do not match. VM: {vm_machine_type}, VMI: {vmi_machine_type}"

    assert (
        vm_machine_type != ""
    ), f"Machine type does not exist in VM: {vm_machine_type}"
