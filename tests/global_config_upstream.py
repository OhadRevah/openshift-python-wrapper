import pytest_testconfig


global config
global_config = pytest_testconfig.load_python("tests/global_config.py", "utf-8")

no_unprivileged_client = True
distribution = "upstream"
hco_namespace = "kubevirt-hyperconverged"
sriov_namespace = "sriov-network-operator"

test_guest_performance = {"bandwidth": 2.5}
test_performance_over_pod_network = {"bandwidth": 2.5}
template_defaults = {
    "linux_bridge_cni_name": "bridge",
    "bridge_tuning_name": "tuning",
}

default_storage_class = "local"
default_volume_mode = "Filesystem"

region = "USA"

bridge_device_matrix = ["linux-bridge"]
storage_class_matrix = [
    {"local": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
]
link_aggregation_mode_matrix = [
    "active-backup",
    "balance-tlb",
    "balance-alb",
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
