import os

import pytest_testconfig
from resources.template import Template

from utilities.infra import Images


global config
global_config = pytest_testconfig.load_python(
    py_file="tests/global_config.py", encoding="utf-8"
)

fedora_os_matrix = [
    {
        "fedora-33": {
            "image_name": Images.Fedora.FEDORA33_IMG,
            "image_path": os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA33_IMG),
            "dv_size": Images.Fedora.DEFAULT_DV_SIZE,
            # TODO: Modify to fedora33 once it is added to templates
            "template_labels": {
                "os": "fedora32",
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
