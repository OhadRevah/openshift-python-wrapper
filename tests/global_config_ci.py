import os

import pytest_testconfig
from ocp_resources.template import Template

from utilities.infra import Images


global config
global_config = pytest_testconfig.load_python(
    py_file="tests/global_config.py", encoding="utf-8"
)


no_unprivileged_client = True
hco_namespace = "kubevirt-hyperconverged"
sriov_namespace = "sriov-network-operator"
linux_bridge_cni = "bridge"
bridge_tuning = "tuning"
region = "EMEA"

default_storage_class = "local"

storage_class_matrix = [
    {"local": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
]

fedora_os_matrix = [
    {
        "fedora-33": {
            "image_name": Images.Fedora.FEDORA33_IMG,
            "image_path": os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA33_IMG),
            "dv_size": Images.Fedora.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "fedora33",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
]
for _dir in dir():
    val = locals()[_dir]
    if not (
        isinstance(val, bool)
        or isinstance(val, list)
        or isinstance(val, dict)
        or isinstance(val, str)
    ):
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
