import os

from utilities.infra import Images


global config

no_unprivileged_client = True
distribution = "upstream"
hco_namespace = "kubevirt-hyperconverged"

test_guest_performance = {"bandwidth": 2.5}
test_performance_over_pod_network = {"bandwidth": 2.5}
template_defaults = {
    "linux_bridge_cni_name": "bridge",
    "bridge_tuning_name": "tuning",
}

default_storage_class = "local"
default_volume_mode = "Filesystem"

latest_rhel_version = {
    "os_label": "rhel8.1",
    "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_1_IMG),
}
latest_windows_version = {
    "os_label": "win2k19",
    "image": os.path.join(Images.Windows.DIR, Images.Windows.WIN19_IMG),
}
latest_fedora_version = {
    "os_label": "fedora31",
    "image": os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA31_IMG),
}
windows_username = "Administrator"
windows_password = "Heslo123"

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
