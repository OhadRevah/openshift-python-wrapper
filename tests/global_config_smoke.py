import pytest_testconfig


global config
global_config = pytest_testconfig.load_python(
    py_file="tests/global_config.py", encoding="utf-8"
)

latest_fedora_os_dict = config["latest_fedora_version"]  # noqa: F821
latest_fedora_os_name = latest_fedora_os_dict["template_labels"]["os"]
fedora_os_matrix = [{latest_fedora_os_name: latest_fedora_os_dict}]

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
