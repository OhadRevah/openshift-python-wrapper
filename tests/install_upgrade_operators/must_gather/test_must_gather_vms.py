import logging
import re

import pytest

from tests.install_upgrade_operators.must_gather.utils import (
    assert_files_exists_for_running_vms,
    assert_must_gather_stopped_vm_yaml_file_collection,
    assert_path_not_exists_for_stopped_vms,
)


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


@pytest.mark.usefixtures("must_gather_stopped_vms")
class TestMustGatherStoppedVmDetails:
    @pytest.mark.polarion("CNV-9039")
    def test_must_gather_stopped_vm(
        self,
        must_gather_vms_alternate_namespace_base_path,
        must_gather_vms_from_alternate_namespace,
        must_gather_stopped_vms,
    ):
        """
        Test must-gather collects information for stopped virtual machines.
        Also test colletion of other files of running virtual machines.
        """
        assert_must_gather_stopped_vm_yaml_file_collection(
            base_path=must_gather_vms_alternate_namespace_base_path,
            must_gather_stopped_vms=must_gather_stopped_vms,
        )
        running_vms = list(
            set(must_gather_vms_from_alternate_namespace) - set(must_gather_stopped_vms)
        )
        assert_files_exists_for_running_vms(
            base_path=must_gather_vms_alternate_namespace_base_path,
            running_vms=running_vms,
        )

        assert_path_not_exists_for_stopped_vms(
            base_path=must_gather_vms_alternate_namespace_base_path,
            stopped_vms=must_gather_stopped_vms,
        )
