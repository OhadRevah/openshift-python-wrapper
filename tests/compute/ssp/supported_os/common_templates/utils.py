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
from ocp_resources import pod
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from packaging import version

from tests.compute.ssp.supported_os.utils import (
    get_linux_guest_agent_version,
    guest_agent_version_parser,
)
from tests.compute.utils import get_windows_timezone, vm_started
from utilities.infra import run_ssh_commands
from utilities.virt import (
    get_guest_os_info,
    run_virtctl_command,
    wait_for_ssh_connectivity,
    wait_for_vm_interfaces,
)


HVINFO_PATH = "C:\\\\hvinfo\\\\hvinfo.exe"
LOGGER = logging.getLogger(__name__)


def stop_start_vm(vm, wait_for_interfaces=True):
    vm.stop(wait=True)
    vm_started(vm=vm, wait_for_interfaces=wait_for_interfaces)


def reboot_vm(vm):
    try:
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split("powershell restart-computer -force"),
        )[0]
    # When a reboot command is executed, a resources.pod.ExecOnPodError exception is raised:
    # "connection reset by peer"
    except pod.ExecOnPodError as e:
        if "connection reset by peer" in e.out:
            pass


def vm_os_version(vm):
    """Verify VM os version using SSH"""

    # vm.name format is <os type>-<os major version>[-<minor version>-]<random>-<random>
    # For example: fedora-32-1601036283-2909632 or rhel-8-2-1601034311-6416788
    # The os version in /etc/redhat-release is formated as <os major version>.[<minor version>]
    # For example: 7.6 or 32 (for Fedora)
    os_release_name = vm.name.split("-")[0]
    # Replace rhel with "redhat"
    os_name = "redhat" if "rhel" in os_release_name else os_release_name
    os = re.search(r"(\w+-)?(\d+(-\d+)?)(-\d+-\d+)$", vm.name).group(2)
    command = shlex.split(f"cat /etc/{os_name}-release | grep {os.replace('-', '.')}")

    run_ssh_commands(host=vm.ssh_exec, commands=command)


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
        wait_timeout=180,
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
    """Verify HyperV values in VMI"""

    # TODO: Add evmcs for fedora and Windows hyperV features, once merged
    # https://bugzilla.redhat.com/show_bug.cgi?id=1952551
    hyperv_features_list = [
        "relaxed",
        "vapic",
        "spinlocks",
        "vpindex",
        "synic",
        "stimer",  # synictimer in VM yaml
        "frequencies",
        "ipi",
        "reenlightenment",
        "reset",
        "runtime",
        "tlbflush",
    ]

    hyperv_features = vm.vmi.xml_dict["domain"]["features"]["hyperv"]
    failed_hyeperv_features = [
        hyperv_features[feature]
        for feature in hyperv_features_list
        if hyperv_features[feature]["@state"] != "on"
    ]
    spinlocks_retries_value = hyperv_features["spinlocks"]["@retries"]
    if int(spinlocks_retries_value) != 8191:
        failed_hyeperv_features.append(spinlocks_retries_value)

    stimer_direct_feature = hyperv_features["stimer"]["direct"]
    if stimer_direct_feature["@state"] != "on":
        failed_hyeperv_features.append(hyperv_features["stimer"])

    assert not failed_hyeperv_features, (
        f"The following hyperV flags are not set correctly in VM spec: {failed_hyeperv_features},"
        f"hyperV features in VM spec: {hyperv_features}"
    )


def check_vm_xml_clock(vm):
    """Verify clock values in VMI"""

    clock_timer_list = vm.vmi.xml_dict["domain"]["clock"]["timer"]
    assert [i for i in clock_timer_list if i["@name"] == "hpet"][0]["@present"] == "no"
    assert [i for i in clock_timer_list if i["@name"] == "hypervclock"][0][
        "@present"
    ] == "yes"


def check_windows_vm_hvinfo(vm):
    """Verify HyperV values in Windows VMI using hvinfo"""

    def _check_hyperv_recommendations():
        # TODO: Add NestedEVMCS once https://bugzilla.redhat.com/show_bug.cgi?id=1952551 is merged
        hyperv_windows_recommendations_list = [
            "RelaxedTiming",
            "MSRAPICRegisters",
            "HypercallRemoteTLBFlush",
            "SyntheticClusterIPI",
        ]
        failed_recommendations = []
        vm_recommendations_dict = hvinfo_dict["Recommendations"]
        failed_vm_recommendations = [
            feature
            for feature in hyperv_windows_recommendations_list
            if not vm_recommendations_dict[feature]
        ]

        if failed_vm_recommendations:
            failed_recommendations.append(failed_vm_recommendations)

        spinlocks = vm_recommendations_dict["SpinlockRetries"]
        if int(spinlocks) != 8191:
            failed_recommendations.append(f"SpinlockRetries: {spinlocks}")

        return failed_recommendations

    def _check_hyperv_privileges():
        hyperv_windows_privileges_list = [
            "AccessReenlightenmentControls",
            "AccessVpRunTimeRegs",
            "AccessSynicRegs",
            "AccessSyntheticTimerRegs",
            "AccessVpIndex",
        ]
        vm_privileges_dict = hvinfo_dict["Privileges"]
        return [
            feature
            for feature in hyperv_windows_privileges_list
            if not vm_privileges_dict[feature]
        ]

    def _check_hyperv_features():
        hyperv_windows_features_list = ["TimerFrequenciesQuery"]
        vm_features_dict = hvinfo_dict["Features"]
        return [
            feature
            for feature in hyperv_windows_features_list
            if not vm_features_dict[feature]
        ]

    hvinfo_dict = None

    sampler = TimeoutSampler(
        wait_timeout=90,
        sleep=15,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=[HVINFO_PATH],
    )
    for sample in sampler:
        output = sample[0]
        if output and "connect: connection refused" not in output:
            hvinfo_dict = json.loads(output)
            break

    failed_windows_hyperv_list = _check_hyperv_recommendations()
    failed_windows_hyperv_list.extend(_check_hyperv_privileges())
    failed_windows_hyperv_list.extend(_check_hyperv_features())

    if not hvinfo_dict["HyperVsupport"]:
        failed_windows_hyperv_list.extend("HyperVsupport")

    assert not failed_windows_hyperv_list, (
        f"The following hyperV flags are not set correctly in the guest: {failed_windows_hyperv_list}\n"
        f"VM hvinfo dict:{hvinfo_dict}"
    )


def set_vm_tablet_device_dict(tablet_params):
    """Generates VM tablet device dict"""

    return {
        "spec": {
            "template": {"spec": {"domain": {"devices": {"inputs": [tablet_params]}}}}
        }
    }


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


def add_windows_license(vm, windows_license):
    LOGGER.info("Add Windows license.")
    cmd = shlex.split(
        f"cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /ipk {windows_license}"
    )
    addition_status = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0]
    assert re.match(
        r"Installed product key [a-z0-9-]+ successfully.",
        addition_status,
        re.IGNORECASE,
    ), "Failed to add license."


def activate_windows_online(vm):
    LOGGER.info("Activate Windows license online.")
    cmd = shlex.split("cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /ato")
    online_activation_status = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0]
    assert re.match(
        r"Activating Windows\(R\), (ServerStandard|Professional) edition "
        r"\(.*\) \.+.*Product activated successfully",
        online_activation_status,
        re.DOTALL,
    ), "Failed to activate Windows online."


def is_windows_activated(vm):
    """Returns True if license is active else False"""

    cmd = shlex.split("cscript /NoLogo %systemroot%\\\\system32\\\\slmgr.vbs /xpr")
    return (
        "The machine is permanently activated"
        in run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0]
    )


def check_windows_activated_license(vm, reset_action):
    """Verify VM activation mode after VM reset (reboot / stop and start)"""

    if "stop_start" in reset_action:
        stop_start_vm(vm=vm, wait_for_interfaces=False)
    if "reboot" in reset_action:
        reboot_vm(vm=vm)
    wait_for_vm_interfaces(vmi=vm.vmi, timeout=1800)
    wait_for_ssh_connectivity(vm=vm)
    assert is_windows_activated(vm=vm), "VM license is not activated after restart."


def add_activate_windows_license(vm, license_key):
    """Add Windows license to the VM, activate it online and verify that
    the activation was successful.
    """

    add_windows_license(vm=vm, windows_license=license_key)
    activate_windows_online(vm=vm)
    assert is_windows_activated(vm=vm), "VM license is not activated."


def fetch_osinfo_memory(osinfo_file_path, memory_test, resources_arch):
    """Fetch memory min and max values from the osinfo files."""

    xml_doc = ElementTree.parse(osinfo_file_path)
    root = xml_doc.getroot()
    resources = root.findall("./os/resources")
    return [
        int(resource.findtext(f"./{memory_test}/ram"))
        for resource in resources
        if resources_arch == resource.attrib["arch"]
    ]


def validate_memory(memory_test, template_memory_value, osinfo_memory_value):
    """Validate the minimum and maximum memory values."""
    if memory_test == "minimum":
        return bitmath.parse_string_unsafe(template_memory_value) >= bitmath.Byte(
            osinfo_memory_value
        )
    elif memory_test == "maximum":
        return bitmath.parse_string_unsafe(template_memory_value) < bitmath.Byte(
            osinfo_memory_value
        )


def download_and_extract_tar(tarfile_url):
    """Download and Extract the tar file."""

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

        validation_map = json.loads(
            template.instance.to_dict()["objects"][0]["metadata"]["annotations"][
                "vm.kubevirt.io/validations"
            ]
        )
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
    """VM and VMI should have machine type; machine type cannot be empty"""

    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert (
        vm_machine_type == vmi_machine_type
    ), f"VM and VMI machine type do not match. VM: {vm_machine_type}, VMI: {vmi_machine_type}"

    assert (
        vm_machine_type != ""
    ), f"Machine type does not exist in VM: {vm_machine_type}"


def restart_qemu_guest_agent_service(vm):
    # Service restart is needed because of bugs 1910326 and 1845127
    # TODO: remove restart_qemu_guest_agent_service when tested opering systems are updated with newer qemu KVM
    # and qemu guest agent versions.
    qemu_kvm_version = vm.vmi.virt_launcher_pod.execute(
        command=["/usr/libexec/qemu-kvm", "--version", "|", "grep", "kvm"],
        container="compute",
    )
    qemu_guest_agent_version = get_linux_guest_agent_version(ssh_exec=vm.ssh_exec)
    if version.parse(qemu_kvm_version.split()[3]) >= version.parse(
        "5.1.0"
    ) and version.parse(qemu_guest_agent_version) >= version.parse("4.2.0-40"):
        return

    LOGGER.warning(
        f"Restart qemu-guest-agent service, qemu KVM version: {qemu_kvm_version},"
        f"qemu-guest-agent version: {qemu_guest_agent_version}"
    )
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("sudo systemctl restart qemu-guest-agent"),
    )


# Guest agent data comparison functions.
def validate_os_info_virtctl_vs_linux_os(vm):
    def _get_os_info(vm):
        virtctl_info = get_virtctl_os_info(vm=vm)
        cnv_info = get_cnv_os_info(vm=vm)
        libvirt_info = get_libvirt_os_info(vm=vm)
        linux_info = get_linux_os_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    os_info_sampler = TimeoutSampler(
        wait_timeout=330, sleep=30, func=_get_os_info, vm=vm
    )
    check_guest_agent_sampler_data(sampler=os_info_sampler)


def validate_fs_info_virtctl_vs_linux_os(vm):
    def _get_fs_info(vm):
        virtctl_info = get_virtctl_fs_info(vm=vm)
        cnv_info = get_cnv_fs_info(vm=vm)
        libvirt_info = get_libvirt_fs_info(vm=vm)
        linux_info = get_linux_fs_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    virtctl_info = cnv_info = libvirt_info = linux_info = None

    fs_info_sampler = TimeoutSampler(wait_timeout=90, sleep=1, func=_get_fs_info, vm=vm)

    try:
        for virtctl_info, cnv_info, libvirt_info, linux_info in fs_info_sampler:
            if virtctl_info:
                orig_virtctl_info = virtctl_info.copy()
                orig_linux_info = linux_info.copy()

                # Disk usage may not be bit exact; allowing up to 5% diff
                disk_usage_diff_validation = (
                    1 - virtctl_info.pop("used") / linux_info.pop("used") <= 0.05
                )
                # total usage - allowing up to 5% diff for ext4 FS
                disk_total_diff_validation = (
                    1 - virtctl_info.pop("total") / linux_info.pop("total") <= 0.05
                    if virtctl_info["fsType"] == "ext4"
                    else virtctl_info.pop("total") == linux_info.pop("total")
                )
                if (
                    disk_usage_diff_validation
                    and disk_total_diff_validation
                    and virtctl_info == linux_info
                ):
                    return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Data mismatch!\nVirtctl: {orig_virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\n"
            f"OS: {orig_linux_info}"
        )
        raise


def validate_user_info_virtctl_vs_linux_os(vm):
    def _get_user_info(vm):
        virtctl_info = get_virtctl_user_info(vm=vm)
        cnv_info = get_cnv_user_info(vm=vm)
        libvirt_info = get_libvirt_user_info(vm=vm)
        linux_info = get_linux_user_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    user_info_sampler = TimeoutSampler(
        wait_timeout=30, sleep=10, func=_get_user_info, vm=vm
    )
    check_guest_agent_sampler_data(sampler=user_info_sampler)


def validate_os_info_vmi_vs_linux_os(vm):
    vmi_info = get_guest_os_info(vmi=vm.vmi)
    linux_info = get_linux_os_info(ssh_exec=vm.ssh_exec)["os"]
    del linux_info["machine"]  # VMI describe doesn't have machine info
    linux_info["version"] = linux_info["version"].split(" ")[0]

    assert vmi_info == linux_info, f"Data mismatch! VMI: {vmi_info}\nOS: {linux_info}"


def validate_os_info_virtctl_vs_windows_os(vm):
    virtctl_info = get_virtctl_os_info(vm=vm)
    cnv_info = get_cnv_os_info(vm=vm)
    libvirt_info = get_libvirt_os_info(vm=vm)
    windows_info = get_windows_os_info(ssh_exec=vm.ssh_exec)

    data_mismatch = []
    if version.parse(virtctl_info["guestAgentVersion"]) != version.parse(
        windows_info["guestAgentVersion"]
    ):
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


def validate_fs_info_virtctl_vs_windows_os(vm):
    def _get_fs_info(vm):
        virtctl_info = get_virtctl_fs_info(vm=vm)
        cnv_info = get_cnv_fs_info(vm=vm)
        libvirt_info = get_libvirt_fs_info(vm=vm)
        windows_info = get_windows_fs_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, windows_info

    virtctl_info = cnv_info = libvirt_info = windows_info = None
    fs_info_sampler = TimeoutSampler(
        wait_timeout=330, sleep=30, func=_get_fs_info, vm=vm
    )

    try:
        for virtctl_info, cnv_info, libvirt_info, windows_info in fs_info_sampler:
            if virtctl_info:
                if all([str(val) in windows_info for val in virtctl_info.values()]):
                    return

    except TimeoutExpiredError:
        raise ValueError(
            f"Data mismatch!\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
        )


def validate_user_info_virtctl_vs_windows_os(vm):
    def _get_vm_timezone_diff():
        vm_timezone_diff = get_virtctl_os_info(vm=vm)["timezone"]
        # Get timezone diff from UTC
        # For example: 'Pacific Standard Time, -28800' -> return 28800
        return int(re.search(r".*, -(\d+)", vm_timezone_diff).group(1))

    virtctl_info = get_virtctl_user_info(vm=vm)
    cnv_info = get_cnv_user_info(vm=vm)
    libvirt_info = get_libvirt_user_info(vm=vm)
    windows_info = run_ssh_commands(host=vm.ssh_exec, commands=["quser"])[0]

    # Match timezone to VM's timezone and not use UTC
    virtctl_time = virtctl_info["loginTime"] - _get_vm_timezone_diff()
    data_mismatch = []
    if virtctl_info["userName"].lower() not in windows_info:
        data_mismatch.append("user name mismatch")
    # Windows date format - 11/4/2020 (-m/-d/Y)
    if (
        datetime.utcfromtimestamp(virtctl_time).strftime("%-m/%-d/%Y")
        not in windows_info
    ):
        data_mismatch.append("login time mismatch")

    assert not data_mismatch, (
        f"Data mismatch {data_mismatch}!"
        f"\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
    )


def validate_os_info_vmi_vs_windows_os(vm):
    vmi_info = get_guest_os_info(vmi=vm.vmi)
    assert vmi_info, "VMI doesn't have guest agent data"
    cmd = shlex.split(
        "wmic os get BuildNumber, Caption, OSArchitecture, Version /value"
    )
    windows_info = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0]

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
    res, output, err = run_virtctl_command(command=cmd, namespace=vm.namespace)
    if not res:
        LOGGER.error(f"Failed to get guest-agent info via virtctl. Error: {err}")
        return
    data = json.loads(output)
    # virtctl gusetosinfo also returns filesystem and user info (if any active user is logged in)
    # here they are deleted for easy compare vs data from get_linux_os_info() & get_libvirt_os_info()
    # fsInfo and userList values are checked in other tests
    data.pop("supportedCommands", None)
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


def get_linux_os_info(ssh_exec):
    # Use guest agent version without the build number
    ga_ver = get_linux_guest_agent_version(ssh_exec=ssh_exec).split("-")[0]
    hostname = ssh_exec.network.hostname
    os_release = ssh_exec.os.release_info
    kernel = ssh_exec.os.kernel_info
    timezone = ssh_exec.os.timezone

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


def get_windows_os_info(ssh_exec):
    ga_ver_cmd = shlex.split(
        'wmic datafile "C:\\\\\\\\Program Files\\\\\\\\Qemu-ga\\\\\\\\qemu-ga.exe" get Version /value'
    )
    ga_ver = run_ssh_commands(host=ssh_exec, commands=ga_ver_cmd)[0].strip()
    hostname_cmd = shlex.split("wmic os get CSName /value")
    hostname = run_ssh_commands(host=ssh_exec, commands=hostname_cmd)[0]
    os_release_cmd = shlex.split(
        "wmic os get BuildNumber, Caption, OSArchitecture, Version /value"
    )
    os_release = run_ssh_commands(host=ssh_exec, commands=os_release_cmd)[0]
    timezone = get_windows_timezone(ssh_exec=ssh_exec)

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
        "used": <used bytes>,
        "total": <total bytes>,
    }
    """
    cmd = ["fslist", vm.name]
    res, output, err = run_virtctl_command(command=cmd, namespace=vm.namespace)
    if not res:
        LOGGER.error(f"Failed to get guest-agent info via virtctl. Error: {err}")
        return
    return guest_agent_disk_info_parser(disk_info=json.loads(output)["items"])


def get_cnv_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "used": <used bytes>,
        "total": <total bytes>,
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
        "used": <used bytes>,
        "total": <total bytes>,
    }
    """
    fsinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-fsinfo")
    return guest_agent_disk_info_parser(disk_info=fsinfo)


def get_linux_fs_info(ssh_exec):
    cmd = shlex.split("df -TB1 | grep /dev/vd")
    out = run_ssh_commands(host=ssh_exec, commands=cmd)[0]
    disks = out.strip().split()
    return {
        "name": disks[0].split("/dev/")[1],
        "mount": disks[6],
        "fsType": disks[1],
        "used": int(disks[3]),
        "total": int(disks[2]),
    }


def get_windows_fs_info(ssh_exec):
    disk_name_cmd = shlex.split("fsutil volume list")
    disk_name = run_ssh_commands(host=ssh_exec, commands=disk_name_cmd)[0]
    disk_space_cmd = shlex.split("fsutil volume diskfree C:")
    disk_space = (
        run_ssh_commands(host=ssh_exec, commands=disk_space_cmd)[0]
        .strip()
        .split("\r\n")
    )
    fs_type_cmd = shlex.split("fsutil fsinfo volumeinfo C:")
    fs_type = run_ssh_commands(host=ssh_exec, commands=fs_type_cmd)[0]

    return f"{disk_name} {windows_disk_space_parser(disk_space)} {fs_type}"


def get_virtctl_user_info(vm):
    cmd = ["userlist", vm.name]
    res, output, err = run_virtctl_command(command=cmd, namespace=vm.namespace)
    if not res:
        LOGGER.error(f"Failed to get guest-agent info via virtctl. Error: {err}")
        return
    for user in json.loads(output)["items"]:
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


def get_linux_user_info(ssh_exec):
    cmd = shlex.split("lastlog | grep tty; who | awk \"'{print$3}'\"")
    out = run_ssh_commands(host=ssh_exec, commands=cmd)[0]
    users = out.strip().split()
    date = datetime.strptime(
        f"{users[7]}-{users[3]}-{users[4]} {users[5]}", "%Y-%b-%d %H:%M:%S"
    )
    timestamp = date.replace(
        tzinfo=timezone(timedelta(seconds=int(ssh_exec.os.timezone.offset) * 36))
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
                "used": disk.get("used-bytes", disk.get("usedBytes")),
                "total": disk.get("total-bytes", disk.get("totalBytes")),
            }


def check_guest_agent_sampler_data(sampler):
    virtctl_info = cnv_info = libvirt_info = linux_info = None
    try:
        for virtctl_info, cnv_info, libvirt_info, linux_info in sampler:
            if virtctl_info:
                if virtctl_info == linux_info:
                    return
    except TimeoutExpiredError:
        raise ValueError(
            f"Data mismatch!\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {linux_info}"
        )


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


def validate_virtctl_guest_agent_data_over_time(vm):
    """
    Validates that virtctl guest info is available over time. (BZ 1886453)

    Returns:
        bool: True - if virtctl guest info is available after timeout else False
    """
    samples = TimeoutSampler(wait_timeout=180, sleep=5, func=get_virtctl_os_info, vm=vm)
    try:
        for sample in samples:
            if not sample:
                return False
    except TimeoutExpiredError:
        return True
