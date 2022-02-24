import logging
import re

import pytest


LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures("collected_vm_details_must_gather")
class TestMustGatherVmDetails:
    @pytest.mark.parametrize(
        "extracted_data_from_must_gather_file, format_regex",
        [
            pytest.param(
                {"file_suffix": "bridge.txt", "section_title": "bridge fdb show:"},
                "{mac_address}",
                marks=(pytest.mark.polarion("CNV-2735")),
            ),
            pytest.param(
                {"file_suffix": "bridge.txt", "section_title": "bridge vlan show:"},
                "{interface_name}",
                marks=(pytest.mark.polarion("CNV-2736")),
            ),
            pytest.param(
                {"file_suffix": "ip.txt", "section_title": None},
                "{interface_name}",
                marks=(pytest.mark.polarion("CNV-2734")),
            ),
            pytest.param(
                {"file_suffix": "ruletables.txt", "section_title": None},
                "table ip filter",
                marks=(pytest.mark.polarion("CNV-2737"),),
            ),
            pytest.param(
                {"file_suffix": "ruletables.txt", "section_title": None},
                "table ip nat",
                marks=(pytest.mark.polarion("CNV-2741"),),
            ),
            pytest.param(
                {"file_suffix": "qemu.log", "section_title": None},
                "-name guest={namespace}_{name},debug-threads=on \\\\$",
                marks=(pytest.mark.polarion("CNV-2725")),
            ),
            pytest.param(
                {"file_suffix": "dumpxml.xml", "section_title": None},
                "^ +<name>{namespace}_{name}</name>$",
                marks=(pytest.mark.polarion("CNV-3477")),
            ),
        ],
        indirect=["extracted_data_from_must_gather_file"],
    )
    def test_data_collected_from_virt_launcher(
        self,
        collected_vm_details_must_gather,
        must_gather_vm,
        nad_mac_address,
        vm_interface_name,
        extracted_data_from_must_gather_file,
        format_regex,
    ):
        if "name" in format_regex and "namespace" in format_regex:
            format_regex = format_regex.format(
                namespace=must_gather_vm.namespace, name=must_gather_vm.name
            )
        if "mac_address" in format_regex:
            format_regex = format_regex.format(mac_address=nad_mac_address)
        if "interface_name" in format_regex:
            format_regex = format_regex.format(interface_name=vm_interface_name)
        LOGGER.info(
            f"Results from search: "
            f"{re.search(format_regex, extracted_data_from_must_gather_file, re.MULTILINE | re.IGNORECASE)}"
        )
        # Make sure that gathered data roughly matches expected format.
        assert re.search(
            format_regex,
            extracted_data_from_must_gather_file,
            re.MULTILINE | re.IGNORECASE,
        ), (
            "Gathered data are not matching expected format.\n"
            f"Expected format:\n{format_regex}\n "
            f"Gathered data:\n{extracted_data_from_must_gather_file}"
        )
