import logging
import re
import shlex

import pytest
from pytest_testconfig import py_config
from resources.utils import TimeoutSampler

from tests.compute.utils import get_linux_timezone, get_windows_timezone
from tests.conftest import vm_instance_from_template
from utilities.exceptions import CommandExecFailed
from utilities.infra import run_ssh_commands
from utilities.virt import wait_for_ssh_connectivity, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)

RHEL = "rhel"
WIN = "win"
NEW_TIMEZONE = {
    RHEL: "Antarctica/Troll",
    WIN: "New Zealand Standard Time",
}
NEW_FILENAME = "persistent_file"
NEW_PASSWORD = "General_Ken0bi!"


@pytest.fixture(scope="class")
def persistence_vm(
    request, golden_image_data_volume_scope_class, unprivileged_client, namespace
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_class,
    ) as vm:
        yield vm


@pytest.fixture()
def changed_os_preferences(request, persistence_vm):
    os = request.param
    old_timezone = get_timezone(vm=persistence_vm, os=os)
    old_passwd = persistence_vm.password

    set_timezone(vm=persistence_vm, os=os, timezone=NEW_TIMEZONE[os])
    touch_file(vm=persistence_vm, os=os)
    set_passwd(vm=persistence_vm, os=os, passwd=NEW_PASSWORD)

    yield

    LOGGER.info("Restore configuration")
    set_timezone(vm=persistence_vm, os=os, timezone=old_timezone)
    delete_file(vm=persistence_vm, os=os)
    set_passwd(vm=persistence_vm, os=os, passwd=old_passwd)


@pytest.fixture()
def restarted_persistence_vm(request, persistence_vm):
    restart_type = request.param["restart_type"]
    os = request.param["os"]

    if restart_type == "guest":
        guest_reboot(vm=persistence_vm, os=os)
    elif restart_type == "API":
        LOGGER.info(f"Rebooting {persistence_vm.name} from API")
        persistence_vm.restart(wait=True)

    # wait for the VM to come back up
    wait_for_vm_interfaces(vmi=persistence_vm.vmi)
    wait_for_ssh_connectivity(
        vm=persistence_vm, timeout=1800 if os == WIN else 300, tcp_timeout=120
    )


def run_os_command(vm, command):
    try:
        return run_ssh_commands(host=vm.ssh_exec, commands=shlex.split(command))[0]
    except CommandExecFailed:
        # On a successful command execution the return code is 0,
        # however on RHEL, a successful reboot command execution return code is -1
        if "reboot" not in command:
            raise


def wait_for_user_agent_down(vm, timeout):
    LOGGER.info(
        f"Waiting up to {round(timeout / 60)} minutes for user agent to go down on {vm.name}"
    )
    for sample in TimeoutSampler(
        timeout=timeout,
        sleep=2,
        func=lambda: [
            condition
            for condition in vm.vmi.instance.status.conditions
            if condition["type"] == "AgentConnected"
        ],
    ):
        if not sample:
            break


def get_timezone(vm, os):
    tz = (
        get_linux_timezone(ssh_exec=vm.ssh_exec)
        if os == RHEL
        else get_windows_timezone(ssh_exec=vm.ssh_exec, get_standard_name=True)
    )

    # Outputs are different for RHEL/Windows, need to split differently
    # RHEL: 'Timezone=America/New_York\n'
    # Windows: 'StandardName               : New Zealand Standard Time\r\n'
    timezone = re.search(r".*[=|:][\s]?(.*?)[\r\n]", tz).group(1)
    LOGGER.info(f"Current timezone: {timezone}")
    return timezone


def set_timezone(vm, os, timezone):
    commands = {
        RHEL: f"sudo timedatectl set-timezone {timezone}",
        WIN: f"powershell -command \"Set-TimeZone -Id '{timezone}'\"",
    }

    LOGGER.info(f"Setting timezone: {timezone}")
    run_os_command(vm=vm, command=commands[os])

    LOGGER.info("Verifying timezone change")
    assert get_timezone(vm=vm, os=os) == timezone


def touch_file(vm, os):
    commands = {
        RHEL: f"touch {NEW_FILENAME}",
        WIN: f"echo > {NEW_FILENAME}",
    }

    LOGGER.info(f"Creating file: {NEW_FILENAME}")
    run_os_command(vm=vm, command=commands[os])

    LOGGER.info("Verifying file creation")
    assert grep_file(vm=vm, os=os)


def grep_file(vm, os):
    commands = {
        RHEL: f"ls | grep {NEW_FILENAME} ||true",
        WIN: f"dir | findstr {NEW_FILENAME} || ver>nul",
    }
    found_file = run_os_command(vm=vm, command=commands[os])
    return found_file


def delete_file(vm, os):
    commands = {RHEL: f"rm {NEW_FILENAME}", WIN: f"del {NEW_FILENAME}"}
    run_os_command(vm=vm, command=commands[os])
    assert not grep_file(vm=vm, os=os)


def set_passwd(vm, os, passwd):
    commands = {
        RHEL: f"echo {vm.username}:{passwd} | sudo chpasswd",
        WIN: f"net user {vm.username} {passwd}",
    }

    LOGGER.info(f"Setting password: {passwd}")
    run_os_command(vm=vm, command=commands[os])

    # Update the VM object password
    vm.password = passwd

    LOGGER.info("Verifying password change")
    vm.ssh_exec.executor().is_connective()


def guest_reboot(vm, os):
    commands = {
        "stop-user-agent": {
            RHEL: "sudo systemctl stop qemu-guest-agent",
            WIN: "powershell -command \"Stop-Service -Name 'QEMU-GA'\"",
        },
        "reboot": {
            RHEL: "sudo reboot",
            WIN: 'powershell -command "Restart-Computer -Force"',
        },
    }

    LOGGER.info("Stopping user agent")
    run_os_command(vm=vm, command=commands["stop-user-agent"][os])
    wait_for_user_agent_down(vm=vm, timeout=120)

    LOGGER.info(f"Rebooting {vm.name} from guest")
    run_os_command(vm=vm, command=commands["reboot"][os])


def verify_changes(vm, os):
    # Verify passwd change and timezone
    # Password is verified by logging in using the new password
    assert get_timezone(vm=vm, os=os) == NEW_TIMEZONE[os]

    # verify touched file
    assert grep_file(vm=vm, os=os)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, persistence_vm",
    [
        [
            {
                "dv_name": "persistence-rhel-dv",
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "persistence-rhel-vm",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
            },
        ]
    ],
    indirect=True,
)
class TestRestartPersistenceLinux:
    @pytest.mark.parametrize(
        "changed_os_preferences, restarted_persistence_vm",
        [
            pytest.param(
                RHEL,
                {"restart_type": "guest", "os": RHEL},
                marks=pytest.mark.polarion("CNV-5618"),
                id="guest reboot",
            ),
            pytest.param(
                RHEL,
                {"restart_type": "API", "os": RHEL},
                marks=pytest.mark.polarion("CNV-5188"),
                id="API reboot",
            ),
        ],
        indirect=True,
    )
    def test_restart_persistence_linux(
        self, persistence_vm, changed_os_preferences, restarted_persistence_vm
    ):
        verify_changes(vm=persistence_vm, os=RHEL)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, persistence_vm",
    [
        [
            {
                "dv_name": "persistence-windows-dv",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "persistence-windows-vm",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "ssh": True,
                "username": py_config["windows_username"],
                "password": py_config["windows_password"],
            },
        ]
    ],
    indirect=True,
)
class TestRestartPersistenceWindows:
    @pytest.mark.parametrize(
        "changed_os_preferences, restarted_persistence_vm",
        [
            pytest.param(
                WIN,
                {"restart_type": "guest", "os": WIN},
                marks=pytest.mark.polarion("CNV-5617"),
                id="guest reboot",
            ),
            pytest.param(
                WIN,
                {"restart_type": "API", "os": WIN},
                marks=pytest.mark.polarion("CNV-5619"),
                id="API reboot",
            ),
        ],
        indirect=True,
    )
    def test_restart_persistence_windows(
        self, persistence_vm, changed_os_preferences, restarted_persistence_vm
    ):
        verify_changes(vm=persistence_vm, os=WIN)
