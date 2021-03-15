import pytest_testconfig

from utilities.infra import generate_latest_os_dict


global config
global_config = pytest_testconfig.load_python(
    py_file="tests/global_config.py", encoding="utf-8"
)

fedora_os_matrix = [
    dict([generate_latest_os_dict(os_list=config["fedora_os_matrix"])])  # noqa: F821
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
