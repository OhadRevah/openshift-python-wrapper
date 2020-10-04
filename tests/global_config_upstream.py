import pytest_testconfig


global config
global_config = pytest_testconfig.load_python(
    py_file="tests/global_config.py", encoding="utf-8"
)

no_unprivileged_client = True
distribution = "upstream"
hco_namespace = "kubevirt-hyperconverged"
sriov_namespace = "sriov-network-operator"
linux_bridge_cni = "bridge"
bridge_tuning = "tuning"

default_storage_class = "local"

storage_class_matrix = [
    {"local": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
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
