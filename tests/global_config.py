import os

from utilities.infra import Images


global config

no_unprivileged_client = False
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
    "os_version": "19",
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
    "active-backup",
    "balance-tlb",
    "balance-alb",
]

rhel_os_matrix = [
    {
        "rhel-6-10": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL6_IMG),
            "template_labels": {
                "os": "rhel6.0",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-6": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_6_IMG),
            "template_labels": {
                "os": "rhel7.6",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-7": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_7_IMG),
            "template_labels": {
                "os": "rhel7.7",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-8": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_8_IMG),
            # TODO: Modify to 7.8 once it is added to templates
            "template_labels": {
                "os": "rhel7.7",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-9": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_9_IMG),
            # TODO: Modify to 7.9 once it is added to templates
            "template_labels": {
                "os": "rhel7.7",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-0": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_0_IMG),
            "template_labels": {
                "os": "rhel8.0",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-1": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_1_IMG),
            "template_labels": {
                "os": "rhel8.1",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-2": {
            "image": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_2_IMG),
            # TODO: Modify to 8.2 once it is added to templates
            "template_labels": {
                "os": "rhel8.1",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
]

windows_os_matrix = [
    {
        "win-10": {
            "os_version": "10",
            "image": os.path.join(Images.Windows.DIR, Images.Windows.WIM10_IMG),
            "template_labels": {
                "os": "win10",
                "workload": "desktop",
                "flavor": "medium",
            },
            "license": "TFNPT-4HYRB-JMJW3-6JDYQ-JTYP6",
        }
    },
    {
        "win-12": {
            "os_version": "12",
            "image": os.path.join(Images.Windows.DIR, Images.Windows.WIN12_IMG),
            "template_labels": {
                "os": "win2k12r2",
                "workload": "server",
                "flavor": "medium",
            },
            "license": "CKWJN-48TW8-V7CVV-RQCFY-R6XCB",
        }
    },
    {
        "win-16": {
            "os_version": "16",
            "image": os.path.join(Images.Windows.DIR, Images.Windows.WIN16_IMG),
            "template_labels": {
                "os": "win2k16",
                "workload": "server",
                "flavor": "medium",
            },
            "license": "MBHVF-NK7XF-C4YG9-8VBVP-Q3XQF",
        }
    },
    {
        "win-19": {
            "os_version": "19",
            "image": os.path.join(Images.Windows.DIR, Images.Windows.WIN19_IMG),
            "template_labels": {
                "os": "win2k19",
                "workload": "server",
                "flavor": "medium",
            },
            "license": "N8BP4-3RHM3-YQWTF-MBJC3-YBKQ3",
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
