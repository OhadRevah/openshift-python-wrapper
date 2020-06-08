# -*- coding: utf-8 -*-

import json
import logging
import re
import socket
import tarfile
import urllib.request
import xml.etree.ElementTree as EleTree

import bitmath
import rrmngmnt
import utilities.network
from openshift.dynamic.exceptions import NotFoundError
from resources import pod
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.compute.utils import vm_started
from utilities.virt import (
    execute_winrm_cmd,
    vm_console_run_commands,
    wait_for_windows_vm,
)


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


def get_vm_accessible_ip(rhel7_workers, schedulable_node_ips, vm):
    return (
        utilities.network.get_vmi_ip_v4_by_name(vmi=vm.vmi, name=[*vm.networks][0])
        if rhel7_workers
        else list(schedulable_node_ips.values())[0]
    )


def get_vm_ssh_port(rhel7_workers, vm):
    return 22 if rhel7_workers else vm.ssh_node_port


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


def check_windows_activated_license(
    vm, winrmcli_pod, reset_action, version, helper_vm=False
):
    """ Verify VM activation mode after VM reset (reboot / stop and start) """

    if "stop_start" in reset_action:
        stop_start_vm(vm=vm, wait_for_interfaces=False)
    if "reboot" in reset_action:
        reboot_vm(vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm)
    wait_for_windows_vm(
        vm=vm, version=version, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm,
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


def validate_cnv_os_info_vs_libvirt_os_info(vm):
    """ Compare OS data from guest agent subresource vs libvirt data. """
    cnv_os_info = get_cnv_os_info(vm)
    libvirt_os_info = get_libvirt_os_info(vm)

    assert (
        cnv_os_info == libvirt_os_info
    ), f"Data mismatch! CNV data {cnv_os_info}, Libvirt data {libvirt_os_info}"


def validate_cnv_fs_info_vs_libvirt_fs_info(vm):
    """ Compare FS data from guest agent subresource vs libvirt data. """
    cnv_fs_info = get_cnv_fs_info(vm)
    libvirt_fs_info = get_libvirt_fs_info(vm)

    assert (
        cnv_fs_info == libvirt_fs_info
    ), f"Data mismatch! CNV data {cnv_fs_info}, Libvirt data {libvirt_fs_info}"


def validate_cnv_os_info_vs_linux_os_info(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    """ Compare OS data from guest agent subresource vs Linux guest OS data. """
    cnv_os_info = get_cnv_os_info(vm)
    guest_os_info = get_linux_os_info(
        ssh_usr=ssh_usr, ssh_pass=ssh_pass, ssh_ip=ssh_ip, ssh_port=ssh_port
    )

    assert (
        cnv_os_info == guest_os_info
    ), f"Data mismatch! CNV data {cnv_os_info}, OS data {guest_os_info}"


def validate_cnv_fs_info_vs_linux_fs_info(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    """ Compare FS data from guest agent subresource vs Linux guest OS data. """
    cnv_fs_info = get_cnv_fs_info(vm)
    guest_fs_info = get_linux_fs_info(
        ssh_usr=ssh_usr, ssh_pass=ssh_pass, ssh_ip=ssh_ip, ssh_port=ssh_port
    )

    assert (
        cnv_fs_info == guest_fs_info
    ), f"Data mismatch! CNV data {cnv_fs_info}, OS data {guest_fs_info}"


def validate_cnv_os_info_vs_windows_os_info(vm, winrmcli_pod, helper_vm=False):
    """ Compare OS data from guest agent subresource vs Windows guest OS data. """
    cnv_os_info = get_cnv_os_info(vm)
    guest_os_info = get_windows_os_info(
        vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm
    )

    assert (
        cnv_os_info["guestAgentVersion"] == guest_os_info["guestAgentVersion"]
    ), f"Data mismatch! CNV data {cnv_os_info}, OS data {guest_os_info}"
    assert (
        cnv_os_info["hostname"] == guest_os_info["hostname"]
    ), f"Data mismatch! CNV data {cnv_os_info}, OS data {guest_os_info}"
    assert (
        cnv_os_info["timezone"].split(",")[0] in guest_os_info["timezone"]
    ), f"Data mismatch! CNV data {cnv_os_info}, OS data {guest_os_info}"
    for key, val in cnv_os_info["os"].items():
        if key != "id":
            assert (
                val.split("_")[1] if "machine" in key else val in guest_os_info["os"]
            ), f"Data mismatch! CNV data {val} not in OS data {guest_os_info}"


def validate_cnv_fs_info_vs_windows_fs_info(vm, winrmcli_pod, helper_vm=False):
    """ Compare FS data from guest agent subresource vs Windows guest OS data. """
    cnv_fs_info = get_cnv_fs_info(vm)
    guest_fs_info = get_windows_fs_info(
        vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm
    )

    for _key, val in cnv_fs_info.items():
        assert (
            str(val) in guest_fs_info
        ), f"Data mismatch! CNV data {val} not in OS data {guest_fs_info}"


def validate_vmi_ga_info_vs_linux_os_info(vm, ssh_usr, ssh_pass, ssh_ip, ssh_port):
    """ Compare OS data from VMI object vs Linux guest OS data. """
    vmi_info = dict(vm.vmi.guest_os_info)
    os_info = get_linux_os_info(
        ssh_usr=ssh_usr, ssh_pass=ssh_pass, ssh_ip=ssh_ip, ssh_port=ssh_port
    )["os"]
    del os_info["machine"]  # VMI describe doesn't have machine info
    os_info["version"] = os_info["version"].split(" ")[0]

    assert vmi_info == os_info, f"Data mismatch! VMI data {vmi_info}, OS data {os_info}"


def validate_vmi_ga_info_vs_windows_os_info(vm, winrmcli_pod, helper_vm=False):
    """ Compare OS data from VMI object vs Windows guest OS data. """
    vmi_info = dict(vm.vmi.guest_os_info)
    os_info = get_windows_os_release(vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm)

    for key, val in vmi_info.items():
        if key != "id":
            assert (
                val.split("r")[0] if "version" in key else val in os_info
            ), f"Data mismatch! VMI data {val} not in OS data {os_info}"


def get_windows_os_info(vm, winrmcli_pod, helper_vm=False):
    """ Gets Windows OS info via winrm-cli. """
    ga_ver = get_windows_guest_agent_version(
        vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm
    ).strip()
    hostname = get_windows_hostname(vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm)
    os_release = get_windows_os_release(
        vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm
    )
    timezone = get_windows_timezone(vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm)

    return {
        "guestAgentVersion": guest_version_extractor(ga_ver),
        "hostname": hostname.strip().split("=")[1],
        "os": os_release,
        "timezone": timezone,
    }


def get_windows_fs_info(vm, winrmcli_pod, helper_vm=False):
    """ Gets Windows filesystem info via winrm-cli. """
    disk_name = get_windows_volume_list(
        vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm
    )
    disk_space = (
        get_windows_volume_space(vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm)
        .strip()
        .split("\r\n")
    )
    fs_type = get_windows_volume_info(
        vm=vm, winrm_pod=winrmcli_pod, helper_vm=helper_vm
    )

    return f"{disk_name} {windows_disk_space_extractor(disk_space)} {fs_type}"


def get_windows_guest_agent_version(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = 'wmic datafile \\"C:\\\\\\\\Program Files\\\\\\\\Qemu-ga\\\\\\\\qemu-ga.exe\\" get Version /value'
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_windows_hostname(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = "wmic os get CSName /value"
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_windows_os_release(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = "wmic os get BuildNumber, Caption, OSArchitecture, Version /value"
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_windows_timezone(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = 'powershell -command "Get-TimeZone"'
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_windows_volume_list(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = "fsutil volume list"
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_windows_volume_space(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = "fsutil volume diskfree C:"
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_windows_volume_info(vm, winrm_pod, helper_vm=False):
    vmi_ip = vm.vmi.virt_launcher_pod.instance.status.podIP
    cmd = "fsutil fsinfo volumeinfo C:"
    return execute_winrm_cmd(
        vmi_ip=vmi_ip,
        winrmcli_pod=winrm_pod,
        cmd=cmd,
        target_vm=vm,
        helper_vm=helper_vm,
    )


def get_linux_os_info(ssh_usr, ssh_pass, ssh_ip, ssh_port):
    host = rrmngmnt_host(usr=ssh_usr, passwd=ssh_pass, ip=ssh_ip, port=ssh_port)
    ga_ver = get_linux_guest_agent_version(rrmngmnt_host=host)
    hostname = host.network.hostname
    os_release = host.os.release_info
    kernel = host.os.kernel_info
    timezone = host.os.timezone

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


def get_linux_fs_info(ssh_usr, ssh_pass, ssh_ip, ssh_port):
    host = rrmngmnt_host(usr=ssh_usr, passwd=ssh_pass, ip=ssh_ip, port=ssh_port)
    return get_linux_filesystem(rrmngmnt_host=host)


def get_linux_guest_agent_version(rrmngmnt_host):
    cmd = ["yum", "list", "-q", "installed", "qemu-g*"]
    rc, out, err = rrmngmnt_host.run_command(cmd)
    return guest_version_extractor(out)


def get_linux_filesystem(rrmngmnt_host):
    cmd = ["df", "-TB1", "|", "grep", "/dev/vd"]
    rc, out, err = rrmngmnt_host.run_command(cmd)
    disks = out.strip().split()
    return fsinfo_disk_dict(
        name=disks[0].split("/dev/")[1],
        mount=disks[6],
        fstype=disks[1],
        used=disks[3],
        total=disks[2],
    )


def fsinfo_disk_dict(name, mount, fstype, used, total):
    return {
        "diskName": name,
        "mountPoint": mount,
        "fileSystemType": fstype,
        "usedBytes": round(int(used) / 1024 ** 3, 1),
        "totalBytes": round(int(total) / 1024 ** 4, 1),
    }


def windows_disk_space_extractor(fsinfo_list):
    disk_space = [x.split(": ")[1].split()[0].replace(",", "") for x in fsinfo_list]
    used = round((int(disk_space[1]) - int(disk_space[0])) / 1024 ** 3, 1)
    total = round(int(disk_space[1]) / 1024 ** 4, 1)
    return f"used {used}, total {total}\n"


def execute_virsh_qemu_agent_command(vm, command):
    domain = f"{vm.namespace}_{vm.vmi.name}"
    output = vm.vmi.virt_launcher_pod.execute(
        command=["virsh", "qemu-agent-command", domain, f'{{"execute":"{command}"}}'],
        container="compute",
    )
    return json.loads(output)["return"]


def guest_version_extractor(version_string):
    return re.search(r"[0-9]+\.[0-9]+\.[0-9]+", version_string).group(0)


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


def get_libvirt_fs_info(vm):
    fsinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-fsinfo")
    for disk in fsinfo:
        if disk["mountpoint"] in ("/", "C:\\"):
            return fsinfo_disk_dict(
                name=disk["name"],
                mount=disk["mountpoint"],
                fstype=disk["type"],
                used=disk["used-bytes"],
                total=disk["total-bytes"],
            )


def get_guest_info_from_subresource(vm):
    response = vm.vmi.client.client.request(
        "GET",
        f"{vm.vmi._subresource_api_url}/guestosinfo",
        headers=vm.vmi.client.configuration.api_key,
    )
    # dict format:
    # {"guestAgentVersion", "hostname", "os", "timezone", "fsInfo"}
    return json.loads(response.data)


def get_cnv_os_info(vm):
    os_info = get_guest_info_from_subresource(vm)
    # "fsInfo" key removed for easier comparison vs libvirt os info and guest os info
    del os_info["fsInfo"]
    return os_info


def get_cnv_fs_info(vm):
    fs_info = get_guest_info_from_subresource(vm)["fsInfo"]
    for disk in fs_info["disks"]:
        if disk["mountPoint"] in ("/", "C:\\"):
            return fsinfo_disk_dict(
                name=disk["diskName"],
                mount=disk["mountPoint"],
                fstype=disk["fileSystemType"],
                used=disk["usedBytes"],
                total=disk["totalBytes"],
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


def rrmngmnt_host(usr, passwd, ip, port):
    host = rrmngmnt.Host(ip)
    host_user = rrmngmnt.user.User(name=usr, password=passwd)
    host._set_executor_user(host_user)
    host.executor_factory = rrmngmnt.ssh.RemoteExecutorFactory(port=port)
    return host
