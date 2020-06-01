import os

from utilities.infra import Images


global config


def _generate_latest_os_dict(os_list):
    """
    Args:
        os_list (list): [rhel|windows|fedora]_os_matrix - a list of dicts

    Returns:
        dict: Latest supported OS else raises an exception.
    """
    for os_dict in os_list:
        for os_values in os_dict.values():
            if os_values.get("latest"):
                return os_values
    assert False, f"No OS is makred as 'latest': {os_list}"


no_unprivileged_client = False
distribution = "downstream"
hco_namespace = "openshift-cnv"
sriov_namespace = "openshift-sriov-network-operator"
machine_api_namespace = "openshift-machine-api"

test_guest_performance = {"bandwidth": 2.5}
test_performance_over_pod_network = {"bandwidth": 2.5}
linux_bridge_cni = "cnv-bridge"
bridge_tuning = "cnv-tuning"

default_storage_class = "nfs"
default_volume_mode = "Filesystem"

provider_matrix = [
    {
        "rhv44": {
            "type": "rhv",
            "version": "4.4",
            "fqdn": "rhev-blue-01.rdu2.scalelab.redhat.com",
            "api_url": "https://rhev-blue-01.rdu2.scalelab.redhat.com/ovirt-engine/api",
            "username": "admin@internal",
            "password": "qum5net",
            "cluster_name": "iscsi",
        }
    },
]

windows_username = "Administrator"
windows_password = "Heslo123"

region = "USA"
usa_server = "cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com"
emea_server = "cnv-qe-server.scl.lab.tlv.redhat.com"
USA = {
    "http_server": f"http://{usa_server}/files/",
    "https_server": f"https://{usa_server}/files/",
    "http_server_auth": f"http://{usa_server}/files/mod-auth-basic/",
    "registry_server": f"docker://{usa_server}",
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

nic_models_matrix = [
    "virtio",
    "e1000e",
]
bridge_device_matrix = ["linux-bridge"]
storage_class_matrix = [
    {
        "hostpath-provisioner": {
            "volume_mode": "Filesystem",
            "access_mode": "ReadWriteOnce",
        }
    },
    {"nfs": {"volume_mode": "Filesystem", "access_mode": "ReadWriteMany"}},
    {
        "ocs-storagecluster-ceph-rbd": {
            "volume_mode": "Block",
            "access_mode": "ReadWriteMany",
        }
    },
]
link_aggregation_mode_matrix = [
    "active-backup",
    "balance-tlb",
    "balance-alb",
]
link_aggregation_mode_no_connectivity_matrix = [
    "balance-xor",
    "802.3ad",
]

rhel_os_matrix = [
    {
        "rhel-6-10": {
            "image_name": Images.Rhel.RHEL6_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL6_IMG),
            "template_labels": {
                "os": "rhel6.0",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-6": {
            "image_name": Images.Rhel.RHEL7_6_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_6_IMG),
            "template_labels": {
                "os": "rhel7.6",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-7": {
            "image_name": Images.Rhel.RHEL7_7_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_7_IMG),
            "template_labels": {
                "os": "rhel7.7",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-8": {
            "image_name": Images.Rhel.RHEL7_8_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_8_IMG),
            "template_labels": {
                "os": "rhel7.8",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-7-9": {
            "image_name": Images.Rhel.RHEL7_9_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_9_IMG),
            # TODO: Modify to 7.9 once it is added to templates
            "template_labels": {
                "os": "rhel7.8",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-0": {
            "image_name": Images.Rhel.RHEL8_0_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_0_IMG),
            "template_labels": {
                "os": "rhel8.0",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-1": {
            "image_name": Images.Rhel.RHEL8_1_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_1_IMG),
            "template_labels": {
                "os": "rhel8.1",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-2": {
            "image_name": Images.Rhel.RHEL8_2_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_2_IMG),
            "latest": True,
            "template_labels": {
                "os": "rhel8.2",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-3": {
            "image_name": Images.Rhel.RHEL8_3_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_3_IMG),
            # TODO: Modify to 8.3 once it is added to templates
            "template_labels": {
                "os": "rhel8.2",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "rhel-8-4": {
            "image_name": Images.Rhel.RHEL8_4_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_4_IMG),
            # TODO: Modify to 8.4 once it is added to templates
            "template_labels": {
                "os": "rhel8.2",
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
            "image_name": Images.Windows.WIM10_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIM10_IMG),
            "dv_size": "50Gi",
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
            "image_name": Images.Windows.WIN12_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIN12_IMG),
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
            "image_name": Images.Windows.WIN16_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIN16_IMG),
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
            "image_name": Images.Windows.WIN19_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIN19_IMG),
            "latest": True,
            "template_labels": {
                "os": "win2k19",
                "workload": "server",
                "flavor": "medium",
            },
            "license": "N8BP4-3RHM3-YQWTF-MBJC3-YBKQ3",
        }
    },
]

fedora_os_matrix = [
    {
        "fedora-31": {
            "image_name": Images.Fedora.FEDORA31_IMG,
            "image_path": os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA31_IMG),
            "template_labels": {
                "os": "fedora31",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
    {
        "fedora-32": {
            "image_name": Images.Fedora.FEDORA32_IMG,
            "image_path": os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA32_IMG),
            "latest": True,
            "template_labels": {
                "os": "fedora32",
                "workload": "server",
                "flavor": "tiny",
            },
        }
    },
]

latest_rhel_version = _generate_latest_os_dict(os_list=rhel_os_matrix)
latest_windows_version = _generate_latest_os_dict(os_list=windows_os_matrix)
latest_fedora_version = _generate_latest_os_dict(os_list=fedora_os_matrix)

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
