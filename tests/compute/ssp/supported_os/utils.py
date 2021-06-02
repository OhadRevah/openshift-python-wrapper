import re


def guest_agent_version_parser(version_string):
    # Return qemu-guest-agent version (including build number, e.g: "4.2.0-34" or "100.0.0.0" for Windows)
    return re.search(r"[0-9]+\.[0-9]+\.[0-9]+[.|-][0-9]+", version_string).group(0)


def get_linux_guest_agent_version(ssh_exec):
    ssh_exec.sudo = True
    return guest_agent_version_parser(
        version_string=ssh_exec.package_manager.info("qemu-guest-agent")
    )
