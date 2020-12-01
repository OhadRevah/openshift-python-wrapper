# -*- coding: utf-8 -*-

import json
import logging
import re
import shlex
import socket
import tarfile
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import bitmath
from packaging import version
from resources import pod
from resources.utils import TimeoutExpiredError, TimeoutSampler

import utilities.network
from tests.compute.utils import rrmngmnt_host, vm_started
from utilities.virt import (
    execute_winrm_cmd,
    get_guest_os_info,
    run_virtctl_command,
    vm_console_run_commands,
    wait_for_windows_vm,
)


LOGGER = logging.getLogger(__name__)


def stop_start_vm(vm, wait_for_interfaces=True):
    vm.stop(wait=True)
    vm_started(vm=vm, wait_for_interfaces=wait_for_interfaces)


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


def vm_os_version(vm, console_impl):
    """ Verify VM os version using console """

    # vm.name format is <os type>-<os major version>[-<minor version>-]<random>-<random>
    # For example: fedora-32-1601036283-2909632 or rhel-8-2-1601034311-6416788
    # The os version in /etc/redhat-release is formated as <os major version>.[<minor version>]
    # For example: 7.6 or 32 (for Fedora)
    os = re.search(r"(\w+-)?(\d+(-\d+)?)(-\d+-\d+)$", vm.name).group(2)
    command = [f"cat /etc/redhat-release | grep {os.replace('-', '.')}"]

    vm_console_run_commands(console_impl=console_impl, vm=vm, commands=command)


def get_vm_accessible_ip(rhel7_workers, schedulable_node_ips, vm):
    return (
        utilities.network.get_vmi_ip_v4_by_name(vmi=vm.vmi, name=[*vm.networks][0])
        if rhel7_workers
        else list(schedulable_node_ips.values())[0]
    )


def get_vm_ssh_port(rhel7_workers, vm):
    return 22 if rhel7_workers else vm.ssh_service.service_port


def check_telnet_connection(ip, port):
    """Verifies successful telnet connection
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


def check_vm_xml_hyperv(vm):
    """ Verify HyperV values in VMI """

    hyperv_features = vm.vmi.xml_dict["domain"]["features"]["hyperv"]
    assert hyperv_features["relaxed"]["@state"] == "on"
    assert hyperv_features["vapic"]["@state"] == "on"
    assert hyperv_features["spinlocks"]["@state"] == "on"
    assert int(hyperv_features["spinlocks"]["@retries"]) == 8191
    # The below entries do not appear in Windows hyperV
    guest_os_info = get_guest_os_info(vmi=vm.vmi)
    if "Windows" not in guest_os_info["name"]:
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
    """Verifies vm tablet device info in VM XML vs VM instance attributes
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


def check_windows_activated_license(
    vm, winrmcli_pod, reset_action, version, helper_vm=False
):
    """ Verify VM activation mode after VM reset (reboot / stop and start) """

    if "stop_start" in reset_action:
        stop_start_vm(vm=vm, wait_for_interfaces=False)
    if "reboot" in reset_action:
        reboot_vm(vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm)
    wait_for_windows_vm(
        vm=vm,
        version=version,
        winrmcli_pod=winrmcli_pod,
        helper_vm=helper_vm,
    )
    assert is_windows_activated(
        vm, winrmcli_pod, helper_vm
    ), "VM license is not activated after restart."


def add_activate_windows_license(vm, winrm_pod, license_key, helper_vm=False):
    """Add Windows license to the VM, activate it online and verify that
    the activation was successful.
    """

    add_windows_license(
        vm=vm, winrmcli_pod=winrm_pod, windows_license=license_key, helper_vm=helper_vm
    )
    activate_windows_online(
        vm=vm,
        winrmcli_pod=winrm_pod,
        helper_vm=helper_vm,
    )
    assert is_windows_activated(vm=vm, winrmcli_pod=winrm_pod, helper_vm=helper_vm), (
        "VM license is not " "activated."
    )


def fetch_osinfo_memory(osinfo_file_path, memory_test, resources_arch):
    """ Fetch memory min and max values from the osinfo files. """

    xml_doc = ElementTree.parse(osinfo_file_path)
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


def execute_virsh_qemu_agent_command(vm, command):
    domain = f"{vm.namespace}_{vm.vmi.name}"
    output = vm.vmi.virt_launcher_pod.execute(
        command=["virsh", "qemu-agent-command", domain, f'{{"execute":"{command}"}}'],
        container="compute",
    )
    return json.loads(output)["return"]


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


def restart_qemu_guest_agent_service(vm, console_impl):
    ver = vm.vmi.virt_launcher_pod.execute(
        command=["/usr/libexec/qemu-kvm", "--version", "|", "grep", "kvm"],
        container="compute",
    )
    if version.parse(ver.split()[3]) >= version.parse("5.1.0"):
        return

    cmd = ["sudo systemctl restart qemu-guest-agent"]
    if "7.7" in vm.vmi.os_version:
        vm_console_run_commands(
            console_impl=console_impl, vm=vm, commands=cmd, verify_commands_output=False
        )
        console_impl(vm=vm).force_disconnect()
    else:
        vm_console_run_commands(console_impl=console_impl, vm=vm, commands=cmd)


# Guest agent data comparison functions.
def validate_os_info_virtctl_vs_linux_os(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    def _get_os_info(vm, rrmngmnt_host):
        virtctl_info = get_virtctl_os_info(vm=vm)
        cnv_info = get_cnv_os_info(vm=vm)
        libvirt_info = get_libvirt_os_info(vm=vm)
        linux_info = get_linux_os_info(rrmngmnt_host=rrmngmnt_host)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    host = rrmngmnt_host(usr=ssh_usr, passwd=ssh_pass, ip=str(ssh_ip), port=ssh_port)
    os_info_sampler = TimeoutSampler(
        timeout=330, sleep=30, func=_get_os_info, vm=vm, rrmngmnt_host=host
    )
    check_guest_agent_sampler_data(sampler=os_info_sampler)


def validate_fs_info_virtctl_vs_linux_os(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    def _get_fs_info(vm, rrmngmnt_host):
        virtctl_info = get_virtctl_fs_info(vm=vm)
        cnv_info = get_cnv_fs_info(vm=vm)
        libvirt_info = get_libvirt_fs_info(vm=vm)
        linux_info = get_linux_fs_info(rrmngmnt_host=rrmngmnt_host)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    host = rrmngmnt_host(usr=ssh_usr, passwd=ssh_pass, ip=str(ssh_ip), port=ssh_port)
    fs_info_sampler = TimeoutSampler(
        timeout=330, sleep=30, func=_get_fs_info, vm=vm, rrmngmnt_host=host
    )
    check_guest_agent_sampler_data(sampler=fs_info_sampler)


def validate_user_info_virtctl_vs_linux_os(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    def _get_user_info(vm, rrmngmnt_host):
        virtctl_info = get_virtctl_user_info(vm=vm)
        cnv_info = get_cnv_user_info(vm=vm)
        libvirt_info = get_libvirt_user_info(vm=vm)
        linux_info = get_linux_user_info(rrmngmnt_host=rrmngmnt_host)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    host = rrmngmnt_host(usr=ssh_usr, passwd=ssh_pass, ip=str(ssh_ip), port=ssh_port)
    user_info_sampler = TimeoutSampler(
        timeout=30, sleep=10, func=_get_user_info, vm=vm, rrmngmnt_host=host
    )
    check_guest_agent_sampler_data(sampler=user_info_sampler)


def validate_os_info_vmi_vs_linux_os(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    host = rrmngmnt_host(usr=ssh_usr, passwd=ssh_pass, ip=str(ssh_ip), port=ssh_port)
    vmi_info = get_guest_os_info(vmi=vm.vmi)
    linux_info = get_linux_os_info(rrmngmnt_host=host)["os"]
    del linux_info["machine"]  # VMI describe doesn't have machine info
    linux_info["version"] = linux_info["version"].split(" ")[0]

    assert vmi_info == linux_info, f"Data mismatch! VMI: {vmi_info}\nOS: {linux_info}"


def validate_os_info_virtctl_vs_windows_os(vm, winrm_pod, helper_vm=False):
    virtctl_info = get_virtctl_os_info(vm=vm)
    cnv_info = get_cnv_os_info(vm=vm)
    libvirt_info = get_libvirt_os_info(vm=vm)
    windows_info = get_windows_os_info(vm=vm, winrm_pod=winrm_pod, helper_vm=helper_vm)

    data_mismatch = []
    if virtctl_info["guestAgentVersion"] != windows_info["guestAgentVersion"]:
        data_mismatch.append("GA version mismatch")
    if virtctl_info["hostname"] != windows_info["hostname"]:
        data_mismatch.append("hostname mismatch")
    if virtctl_info["timezone"].split(",")[0] not in windows_info["timezone"]:
        data_mismatch.append("timezone mismatch")
    for key, val in virtctl_info["os"].items():
        if key != "id":
            if not (
                val.split("_")[1] if "machine" in key else val in windows_info["os"]
            ):
                data_mismatch.append(f"OS data mismatch - {key}")

    assert not data_mismatch, (
        f"Data mismatch {data_mismatch}!"
        f"\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
    )


def validate_fs_info_virtctl_vs_windows_os(vm, winrm_pod, helper_vm=False):
    def _get_fs_info(vm, winrm_pod, helper_vm):
        virtctl_info = get_virtctl_fs_info(vm=vm)
        cnv_info = get_cnv_fs_info(vm=vm)
        libvirt_info = get_libvirt_fs_info(vm=vm)
        windows_info = get_windows_fs_info(
            vm=vm, winrm_pod=winrm_pod, helper_vm=helper_vm
        )
        return virtctl_info, cnv_info, libvirt_info, windows_info

    virtctl_info = cnv_info = libvirt_info = windows_info = None
    fs_info_sampler = TimeoutSampler(
        timeout=330,
        sleep=30,
        func=_get_fs_info,
        vm=vm,
        winrm_pod=winrm_pod,
        helper_vm=helper_vm,
    )

    try:
        for virtctl_info, cnv_info, libvirt_info, windows_info in fs_info_sampler:
            if virtctl_info:
                if all([str(val) in windows_info for val in virtctl_info.values()]):
                    return

    except TimeoutExpiredError:
        LOGGER.error(
            f"Data mismatch!\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
        )
        raise


def validate_user_info_virtctl_vs_windows_os(vm, winrm_pod, helper_vm=False):
    virtctl_info = get_virtctl_user_info(vm=vm)
    cnv_info = get_cnv_user_info(vm=vm)
    libvirt_info = get_libvirt_user_info(vm=vm)
    windows_info = execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrm_pod,
        cmd="quser",
        target_vm=vm,
        helper_vm=helper_vm,
    )

    data_mismatch = []
    if virtctl_info["userName"].lower() not in windows_info:
        data_mismatch.append("user name mismatch")
    # Windows date format - 11/4/2020 (-m/-d/Y)
    if (
        datetime.utcfromtimestamp(virtctl_info["loginTime"]).strftime("%-m/%-d/%Y")
        not in windows_info
    ):
        data_mismatch.append("login time mismatch")

    assert not data_mismatch, (
        f"Data mismatch {data_mismatch}!"
        f"\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
    )


def validate_os_info_vmi_vs_windows_os(vm, winrm_pod, helper_vm=False):
    vmi_info = get_guest_os_info(vmi=vm.vmi)
    assert vmi_info, "VMI doesn't have guest agent data"
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = "wmic os get BuildNumber, Caption, OSArchitecture, Version /value"
    windows_info = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )

    data_mismatch = []
    for key, val in vmi_info.items():
        if key != "id":
            if not (val.split("r")[0] if "version" in key else val in windows_info):
                data_mismatch.append(f"OS data mismatch - {key}")

    assert (
        not data_mismatch
    ), f"Data mismatch {data_mismatch}!\nVMI: {vmi_info}\nOS: {windows_info}"


# Guest agent info gather functions.
def get_virtctl_os_info(vm):
    """
    Returns OS data dict in format:
    {
        "guestAgentVersion": guestAgentVersion,
        "hostname": hostname,
        "os": {
            "name": name,
            "kernelRelease": kernelRelease,
            "version": version,
            "prettyName": prettyName,
            "versionId": versionId,
            "kernelVersion": kernelVersion,
            "machine": machine,
            "id": id,
        },
        "timezone": timezone",
    }
    """
    cmd = ["guestosinfo", vm.name]
    virtctl_output = wait_for_virtctl_output(cmd=cmd, namespace=vm.namespace)
    data = json.loads(virtctl_output)
    # virtctl gusetosinfo also returns filesystem and user info (if any active user is logged in)
    # here they are deleted for easy compare vs data from get_linux_os_info() & get_libvirt_os_info()
    # fsInfo and userList values are checked in other tests
    data.pop("fsInfo", None)
    data.pop("userList", None)
    return data


def get_cnv_os_info(vm):
    """
    Returns OS data dict in format:
    {
        "guestAgentVersion": guestAgentVersion,
        "hostname": hostname,
        "os": {
            "name": name,
            "kernelRelease": kernelRelease,
            "version": version,
            "prettyName": prettyName,
            "versionId": versionId,
            "kernelVersion": kernelVersion,
            "machine": machine,
            "id": id,
        },
        "timezone": timezone",
    }
    """
    data = vm.vmi.guest_os_info
    # subresource gusetosinfo also returns filesystem and user info (if any active user is logged in)
    # here they are deleted for easy compare vs data from get_linux_os_info() & get_libvirt_os_info()
    # fsInfo and userList values are checked in other tests
    data.pop("fsInfo", None)
    data.pop("userList", None)
    return data


def get_libvirt_os_info(vm):
    agentinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-info")
    hostname = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-host-name")
    osinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-osinfo")
    timezone = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-timezone")

    return {
        "guestAgentVersion": agentinfo["version"],
        "hostname": hostname["host-name"],
        "os": {
            "name": osinfo["name"],
            "kernelRelease": osinfo["kernel-release"],
            "version": osinfo["version"],
            "prettyName": osinfo["pretty-name"],
            "versionId": osinfo["version-id"],
            "kernelVersion": osinfo["kernel-version"],
            "machine": osinfo["machine"],
            "id": osinfo["id"],
        },
        "timezone": f"{timezone['zone']}, {timezone['offset']}",
    }


def get_linux_os_info(rrmngmnt_host):
    ga_ver = guest_agent_version_parser(
        version_string=rrmngmnt_host.run_command(
            shlex.split("yum list -q installed qemu-g*")
        )[1]
    )
    hostname = rrmngmnt_host.network.hostname
    os_release = rrmngmnt_host.os.release_info
    kernel = rrmngmnt_host.os.kernel_info
    timezone = rrmngmnt_host.os.timezone

    return {
        "guestAgentVersion": ga_ver,
        "hostname": hostname,
        "os": {
            "name": os_release["NAME"],
            "kernelRelease": kernel.release,
            "version": os_release["VERSION"],
            "prettyName": os_release["PRETTY_NAME"],
            "versionId": os_release["VERSION_ID"],
            "kernelVersion": kernel.version,
            "machine": kernel.type,
            "id": os_release["ID"],
        },
        "timezone": f"{timezone.name}, {int(timezone.offset) * 36}",
    }


def get_windows_os_info(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    ga_ver_cmd = 'wmic datafile \\"C:\\\\\\\\Program Files\\\\\\\\Qemu-ga\\\\\\\\qemu-ga.exe\\" get Version /value'
    ga_ver = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=ga_ver_cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    ).strip()
    hostname_cmd = "wmic os get CSName /value"
    hostname = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=hostname_cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )
    os_release_cmd = "wmic os get BuildNumber, Caption, OSArchitecture, Version /value"
    os_release = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=os_release_cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )
    timezone_cmd = 'powershell -command "Get-TimeZone"'
    timezone = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=timezone_cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )

    return {
        "guestAgentVersion": guest_agent_version_parser(version_string=ga_ver),
        "hostname": hostname.strip().split("=")[1],
        "os": os_release,
        "timezone": timezone,
    }


def get_virtctl_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "usedGB": usedGB,
        "totalGB": totalGB,
    }
    """
    cmd = ["fslist", vm.name]
    virtctl_output = wait_for_virtctl_output(cmd=cmd, namespace=vm.namespace)
    return guest_agent_disk_info_parser(disk_info=json.loads(virtctl_output)["items"])


def get_cnv_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "usedGB": usedGB,
        "totalGB": totalGB,
    }
    """
    return guest_agent_disk_info_parser(disk_info=vm.vmi.guest_fs_info["items"])


def get_libvirt_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "usedGB": usedGB,
        "totalGB": totalGB,
    }
    """
    fsinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-fsinfo")
    return guest_agent_disk_info_parser(disk_info=fsinfo)


def get_linux_fs_info(rrmngmnt_host):
    cmd = shlex.split("df -TB1 | grep /dev/vd")
    _, out, _ = rrmngmnt_host.run_command(command=cmd)
    disks = out.strip().split()
    return {
        "name": disks[0].split("/dev/")[1],
        "mount": disks[6],
        "fsType": disks[1],
        "usedGB": convert_disk_size(value=int(disks[3]), si_prefix=False),
        "totalGB": convert_disk_size(value=int(disks[2]), si_prefix=False),
    }


def get_windows_fs_info(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    disk_name_cmd = "fsutil volume list"
    disk_name = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=disk_name_cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )
    disk_space_cmd = "fsutil volume diskfree C:"
    disk_space = (
        execute_winrm_cmd(
            vmi_ip=vmi_ip,
            winrmcli_pod=winrm_pod,
            cmd=disk_space_cmd,
            target_vm=vm,
            helper_vm=helper_vm,
        )
        .strip()
        .split("\r\n")
    )
    fs_type_cmd = "fsutil fsinfo volumeinfo C:"
    fs_type = execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=fs_type_cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )

    return f"{disk_name} {windows_disk_space_parser(disk_space)} {fs_type}"


def get_virtctl_user_info(vm):
    cmd = ["userlist", vm.name]
    virtctl_output = wait_for_virtctl_output(cmd=cmd, namespace=vm.namespace)
    for user in json.loads(virtctl_output)["items"]:
        return {
            "userName": user["userName"],
            "loginTime": int(user["loginTime"]),
        }


def get_cnv_user_info(vm):
    for user in vm.vmi.guest_user_info["items"]:
        return {
            "userName": user["userName"],
            "loginTime": int(user["loginTime"]),
        }


def get_libvirt_user_info(vm):
    userinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-users")
    for user in userinfo:
        return {
            "userName": user["user"],
            "loginTime": int(user["login-time"]),
        }


def get_linux_user_info(rrmngmnt_host):
    cmd = shlex.split("lastlog | grep tty; who | awk \"'{print$3}'\"")
    _, out, _ = rrmngmnt_host.run_command(command=cmd)
    users = out.strip().split()
    date = datetime.strptime(f"{users[8]} {users[5]}", "%Y-%m-%d %H:%M:%S")
    timestamp = date.replace(
        tzinfo=timezone(timedelta(seconds=int(rrmngmnt_host.os.timezone.offset) * 36))
    ).timestamp()
    return {
        "userName": users[0],
        "loginTime": int(timestamp),
    }


# Guest agent test related functions.
def guest_agent_disk_info_parser(disk_info):
    for disk in disk_info:
        if disk.get("mountpoint", disk.get("mountPoint")) in ("/", "C:\\"):
            return {
                "name": disk.get("name", disk.get("diskName")),
                "mount": disk.get("mountpoint", disk.get("mountPoint")),
                "fsType": disk.get("type", disk.get("fileSystemType")),
                "usedGB": convert_disk_size(
                    value=disk.get("used-bytes", disk.get("usedBytes"))
                ),
                "totalGB": convert_disk_size(
                    value=disk.get("total-bytes", disk.get("totalBytes"))
                ),
            }


def check_guest_agent_sampler_data(sampler):
    virtctl_info = cnv_info = libvirt_info = linux_info = None
    try:
        for virtctl_info, cnv_info, libvirt_info, linux_info in sampler:
            if virtctl_info:
                if virtctl_info == linux_info:
                    return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Data mismatch!\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {linux_info}"
        )
        raise


def convert_disk_size(value, si_prefix=True):
    value = bitmath.Byte(bytes=value)
    return round(float(value.to_GB() if si_prefix else value.to_GiB()))


def guest_agent_version_parser(version_string):
    return re.search(r"[0-9]+\.[0-9]+\.[0-9]+", version_string).group(0)


def windows_disk_space_parser(fsinfo_list):
    # fsinfo_list contains strings of total free and total bytes in format:
    # ['Total free bytes        :  81,103,310,848 ( 75.5 GB)',
    #  'Total bytes             : 249,381,777,408 (232.3 GB)',
    #  'Total quota free bytes  :  81,103,310,848 ( 75.5 GB)']
    disk_space = {
        "total": re.sub(",", "", re.search(r": (\S*)", fsinfo_list[1]).group(1)),
        "free": re.sub(",", "", re.search(r": (\S*)", fsinfo_list[0]).group(1)),
    }
    used = round((int(disk_space["total"]) - int(disk_space["free"])) / 1000 ** 3)
    total = round(int(disk_space["total"]) / 1000 ** 3)
    return f"used {used}, total {total}\n"


# TODO: Remove once bug 1886453 is fixed
def wait_for_virtctl_output(cmd, namespace):
    for res, output in TimeoutSampler(
        timeout=360,
        sleep=5,
        func=run_virtctl_command,
        command=cmd,
        namespace=namespace,
    ):
        if res:
            return output
        else:
            LOGGER.warning("Retrying to get guest-agent info via virtctl")
