import os

from utilities.infra import Images


global config

no_unprivileged_client = False
bare_metal_cluster = False
distribution = "downstream"
hco_namespace = "openshift-cnv"

test_guest_performance = {"bandwidth": 2.5}
test_performance_over_pod_network = {"bandwidth": 2.5}
template_defaults = {
    "linux_bridge_cni_name": "cnv-bridge",
    "bridge_tuning_name": "cnv-tuning",
}

default_storage_class = "nfs"
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
use_server = "cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com"
emea_server = "cnv-qe-server.scl.lab.tlv.redhat.com"
USA = {
    "http_server": f"http://{use_server}/files/",
    "https_server": f"https://{use_server}/files/",
    "http_server_auth": f"http://{use_server}/files/mod-auth-basic/",
    "registry_server": f"docker://{use_server}",
    "https_cert": "usa_https.crt",
    "registry_cert": "usa_registry.crt",
}
EMEA = {
    "http_server": f"http://{emea_server}/files/",
    "https_server": f"https://{emea_server}/files/",
    "http_server_auth": f"http://{emea_server}/files/mod-auth-basic/",
    "registry_server": f"docker://{emea_server}",
    "https_cert": "emea_https.crt",
    "registry_cert": "emea_registry.crt",
}

bridge_device_matrix = ["linux-bridge"]
storage_class_matrix = [
    {
        "hostpath-provisioner": {
            "volume_mode": "Filesystem",
            "access_mode": "ReadWriteOnce",
        }
    },
    {"nfs": {"volume_mode": "Filesystem", "access_mode": "ReadWriteMany"}},
]
link_aggregation_mode_matrix = [
    "balance-rr",
    "active-backup",
    "balance-xor",
    "broadcast",
    "802.3ad",
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
