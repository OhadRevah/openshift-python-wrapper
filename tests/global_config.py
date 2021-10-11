import os

from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from ocp_resources.virtual_machine import VirtualMachine

from utilities.constants import INTEL, Images
from utilities.infra import get_latest_os_dict_list


global config


def _get_default_storage_class(sc_list):
    """
    Args:
        sc_list (list): storage class dict - a list of dicts

    Returns:
        tuple: (default storage class name, default storage class dict) else raises an exception.
    """
    for sc_dict in sc_list:
        for sc_name, sc_values in sc_dict.items():
            if sc_values.get("default"):
                return sc_name, sc_values
    assert False, f"No SC is marked as 'default': {sc_list}"


no_unprivileged_client = False
distribution = "downstream"
hco_cr_name = "kubevirt-hyperconverged"
hco_namespace = "openshift-cnv"
sriov_namespace = "openshift-sriov-network-operator"
marketplace_namespace = "openshift-marketplace"
machine_api_namespace = "openshift-machine-api"
golden_images_namespace = "openshift-virtualization-os-images"

test_guest_performance = {"bandwidth": 0.8}  # All our servers have 1GiB interfaces.
linux_bridge_cni = "cnv-bridge"
bridge_tuning = "cnv-tuning"
nodes_cpu_architecture = INTEL  # INTEL = "Intel" AMD = "AMD"

provider_matrix = [
    {
        "rhv44": {
            "type": "ovirt",
            "version": "4.4",
            "fqdn": "env-rhv44-mgr.cfme2.lab.eng.rdu2.redhat.com",
            "api_url": "https://env-rhv44-mgr.cfme2.lab.eng.rdu2.redhat.com/ovirt-engine/api",
            "username": "admin@internal",
            "password": "Tux4Linux!",
            "cluster_name": "Default",
        }
    },
    {
        "vsphere65": {
            "type": "vmware",
            "version": "6.5",
            "fqdn": "rhev-node-05.rdu2.scalelab.redhat.com",
            "api_url": "https://rhev-node-05.rdu2.scalelab.redhat.com/sdk",
            "username": "administrator@vsphere.local",
            "password": "Heslo123!",
            "cluster_name": "MTV",
            "thumbprint": "31:14:EB:9E:F1:78:68:10:A5:78:D1:A7:DF:BB:54:B7:1B:91:9F:30",
        }
    },
]

windows_username = "Administrator"
windows_password = "Heslo123"

region = "USA"
server_url = ""  # Send --tc=server_url:<url> to override servers region URL
servers_url = {
    "USA": "cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com",
    "EMEA": "cnv-qe-server.lab.eng.tlv2.redhat.com",
}
servers = {
    "http_server": "http://{server}/files/",
    "https_server": "https://{server}/files/",
    "http_server_auth": "http://{server}/files/mod-auth-basic/",
    "registry_server": "docker://{server}",
    "https_cert": "usa_https.crt",
    "registry_cert": "usa_registry.crt",
}

cnv_registry_sources = {
    "osbs": {
        "cnv_subscription_source": "hco-catalogsource",
        "source_map": "registry-proxy.engineering.redhat.com/rh-osbs",
    },
    "stage": {
        "cnv_subscription_source": "hco-catalogsource",
        "source_map": "registry.stage.redhat.io/container-native-virtualization",
    },
    "production": {
        "cnv_subscription_source": "hco-catalogsource",
    },
}

nic_models_matrix = [
    "virtio",
    "e1000e",
]
bridge_device_matrix = ["linux-bridge"]
storage_class_matrix = [
    {
        StorageClass.Types.HOSTPATH: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWO,
        }
    },
    {
        StorageClass.Types.NFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
        }
    },
    {
        StorageClass.Types.CEPH_RBD: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "default": True,
        }
    },
]

default_storage_class, default_storage_class_configuration = _get_default_storage_class(
    sc_list=storage_class_matrix
)
default_volume_mode = default_storage_class_configuration["volume_mode"]
default_access_mode = default_storage_class_configuration["access_mode"]

link_aggregation_mode_matrix = [
    "active-backup",
    "balance-tlb",
    "balance-alb",
]
link_aggregation_mode_no_connectivity_matrix = [
    "balance-xor",
    "802.3ad",
]

vm_volumes_matrix = ["container_disk_vm", "data_volume_vm"]
run_strategy_matrix = [
    VirtualMachine.RunStrategy.MANUAL,
    VirtualMachine.RunStrategy.ALWAYS,
    VirtualMachine.RunStrategy.HALTED,
    VirtualMachine.RunStrategy.RERUNONFAILURE,
]

sysprep_source_matrix = ["ConfigMap", "Secret"]

rhel_os_matrix = [
    {
        "rhel-6-10": {
            "image_name": Images.Rhel.RHEL6_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL6_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel6.0",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-7-6": {
            "image_name": Images.Rhel.RHEL7_6_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_6_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel7.6",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-7-7": {
            "image_name": Images.Rhel.RHEL7_7_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_7_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel7.7",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-7-8": {
            "image_name": Images.Rhel.RHEL7_8_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_8_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel7.8",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-7-9": {
            "image_name": Images.Rhel.RHEL7_9_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_9_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel7.9",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-0": {
            "image_name": Images.Rhel.RHEL8_0_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_0_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel8.0",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-1": {
            "image_name": Images.Rhel.RHEL8_1_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_1_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel8.1",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-2": {
            "image_name": Images.Rhel.RHEL8_2_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_2_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel8.2",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-3": {
            "image_name": Images.Rhel.RHEL8_3_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_3_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel8.3",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-4": {
            "image_name": Images.Rhel.RHEL8_4_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_4_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "latest": True,
            "template_labels": {
                "os": "rhel8.4",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-5": {
            "image_name": Images.Rhel.RHEL8_5_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_5_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            # TODO: Modify to 8.5 once it is added to templates
            "template_labels": {
                "os": "rhel8.4",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-6": {
            "image_name": Images.Rhel.RHEL8_6_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_6_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            # TODO: Modify to 8.6 once it is added to templates
            "template_labels": {
                "os": "rhel8.4",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-9-0": {
            "image_name": Images.Rhel.RHEL9_0_IMG,
            "image_path": os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL9_0_IMG),
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "rhel9.0",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
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
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "win10",
                "workload": Template.Workload.DESKTOP,
                "flavor": Template.Flavor.MEDIUM,
            },
            "license": "BRNVR-4HQGD-GH2WT-Y2CXR-W8F8R",
        }
    },
    {
        "win-12": {
            "os_version": "12",
            "image_name": Images.Windows.WIN12_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIN12_IMG),
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "win2k12r2",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.MEDIUM,
            },
            "license": "CKN69-V8PF9-KT726-Y23JM-XBRRY",
        }
    },
    {
        "win-16": {
            "os_version": "16",
            "image_name": Images.Windows.WIN16_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIN16_IMG),
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "win2k16",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.MEDIUM,
            },
            "license": "8KHNW-H9K6W-4XXX8-8WKW9-3RT3F",
        }
    },
    {
        "win-19": {
            "os_version": "19",
            "image_name": Images.Windows.WIN19_IMG,
            "image_path": os.path.join(Images.Windows.DIR, Images.Windows.WIN19_IMG),
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "latest": True,
            "template_labels": {
                "os": "win2k19",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.MEDIUM,
            },
            "license": "NQJPH-YJBCM-K9F34-YMKPW-Q7CHQ",
        }
    },
]

fedora_os_matrix = [
    {
        "fedora-34": {
            "image_name": Images.Fedora.FEDORA34_IMG,
            "image_path": os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA34_IMG),
            "dv_size": Images.Fedora.DEFAULT_DV_SIZE,
            "latest": True,
            "template_labels": {
                "os": "fedora34",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
]

centos_os_matrix = [
    {
        "centos-7": {
            "image_name": Images.CentOS.CENTOS7_IMG,
            "image_path": os.path.join(Images.CentOS.DIR, Images.CentOS.CENTOS7_IMG),
            "dv_size": Images.CentOS.DEFAULT_DV_SIZE,
            "template_labels": {
                "os": "centos7.0",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
    {
        "centos-8": {
            "image_name": Images.CentOS.CENTOS8_IMG,
            "image_path": os.path.join(Images.CentOS.DIR, Images.CentOS.CENTOS8_IMG),
            "dv_size": Images.CentOS.DEFAULT_DV_SIZE,
            "latest": True,
            "template_labels": {
                "os": "centos8",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
        }
    },
]

(
    latest_rhel_os_dict,
    latest_windows_os_dict,
    latest_fedora_os_dict,
    latest_centos_os_dict,
) = get_latest_os_dict_list(
    os_list=[rhel_os_matrix, windows_os_matrix, fedora_os_matrix, centos_os_matrix]
)

ip_stack_version_matrix = [
    "ipv4",
    "ipv6",
]

for _dir in dir():
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
