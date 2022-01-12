import os
import re

import pytest

from utilities.infra import BUG_STATUS_CLOSED


@pytest.mark.parametrize(
    ("file_suffix", "section_title", "format_regex"),
    [
        pytest.param(
            "ip.txt", None, "\\A1: lo: .*", marks=(pytest.mark.polarion("CNV-2734"))
        ),
        pytest.param(
            "bridge.txt",
            "bridge fdb show:",
            "^(?:[0-9a-fA-F]:?){12} dev .*$",
            marks=(pytest.mark.polarion("CNV-2735")),
        ),
        pytest.param(
            "bridge.txt",
            "bridge vlan show:",
            ".*1 PVID .*untagged$",
            marks=(pytest.mark.polarion("CNV-2736")),
        ),
        pytest.param(
            "iptables.txt",
            "Filter table:",
            "^Chain INPUT \\(policy ACCEPT\\)$",
            marks=(
                pytest.mark.polarion("CNV-2737"),
                pytest.mark.bugzilla(
                    1959039, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            "iptables.txt",
            "NAT table:",
            "^Chain PREROUTING \\(policy ACCEPT\\)$",
            marks=(
                pytest.mark.polarion("CNV-2741"),
                pytest.mark.bugzilla(
                    1959039, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            "qemu.log",
            None,
            "-name guest={namespace}_{name},debug-threads=on \\\\$",
            marks=(pytest.mark.polarion("CNV-2725")),
        ),
        pytest.param(
            "dumpxml.xml",
            None,
            "^ +<name>{namespace}_{name}</name>$",
            marks=(pytest.mark.polarion("CNV-3477")),
        ),
    ],
)
def test_data_collected_from_virt_launcher(
    cnv_must_gather, running_vm, file_suffix, section_title, format_regex
):
    virt_launcher = running_vm.vmi.virt_launcher_pod

    gathered_data_path = (
        f"{cnv_must_gather}/namespaces/{virt_launcher.namespace}/vms/"
        f"{virt_launcher.name}.{file_suffix}"
    )

    assert os.path.exists(
        gathered_data_path
    ), "Have not found gathered data file on given path"

    with open(gathered_data_path) as f:
        gathered_data = f.read()

    # If the gathered data file consists of multiple sections, extract the one
    # we are interested in.
    if section_title:
        matches = re.findall(
            f"^{section_title}\n"  # title
            "^#+\n"  # title separator
            "(.*?)"  # capture section body
            "(?:^#+\n|\\Z)",  # next title separator or end of data
            gathered_data,
            re.MULTILINE | re.DOTALL,
        )
        assert matches, (
            "Section has not been found in gathered data.\n"
            f"Section title: {section_title}\n"
            f"Gathered data: {gathered_data}"
        )
        gathered_data = matches[0]

    if "name" in format_regex and "namespace" in format_regex:
        format_regex = format_regex.format(
            namespace=running_vm.namespace, name=running_vm.name
        )

    # Make sure that gathered data roughly matches expected format.
    assert re.search(format_regex, gathered_data, re.MULTILINE | re.IGNORECASE), (
        "Gathered data are not matching expected format.\n"
        f"Expected format:\n{format_regex}\n "
        f"Gathered data:\n{gathered_data}"
    )
