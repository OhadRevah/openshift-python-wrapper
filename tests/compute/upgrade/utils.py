import logging

from tests.compute.upgrade.constants import SRC_PVC_NAME
from utilities.constants import TIMEOUT_3MIN
from utilities.exceptions import ResourceMissingFieldError
from utilities.virt import wait_for_ssh_connectivity


LOGGER = logging.getLogger(__name__)


def verify_vms_ssh_connectivity(vms_list):
    ssh_timeout = TIMEOUT_3MIN
    for vm in vms_list:
        wait_for_ssh_connectivity(vm=vm, timeout=ssh_timeout, tcp_timeout=ssh_timeout)


def mismatching_src_pvc_names(pre_upgrade_templates, post_upgrade_templates):
    mismatched_templates = {}
    for template in post_upgrade_templates:
        matching_template = [
            temp for temp in pre_upgrade_templates if temp.name == template.name
        ]

        if matching_template:
            expected = get_src_pvc_default_name(template=matching_template[0])
            found = get_src_pvc_default_name(template=template)

            if found != expected:
                mismatched_templates[template.name] = {
                    "expected": expected,
                    "found": found,
                }

    return mismatched_templates


def get_src_pvc_default_name(template):
    param_value_list = [
        param["value"]
        for param in template.instance.parameters
        if param["name"] == SRC_PVC_NAME
    ]

    if param_value_list:
        return param_value_list[0]

    raise ResourceMissingFieldError(
        f"Template {template.name} does not have a parameter {SRC_PVC_NAME}"
    )
