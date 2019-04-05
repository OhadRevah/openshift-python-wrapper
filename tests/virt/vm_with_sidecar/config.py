# flake8: noqa: F401, F403, F405

from tests.virt.config import *

VM_NAME = "vmi-with-sidecar-hook"
CLOUD_INIT = {
    "bootcmd": ["dnf install -y dmidecode qemu-guest-agent"],
    "runcmd": ["systemctl start qemu-guest-agent"]
}
VMS = {
    VM_NAME: {
        "metadata": {
            "annotations": {
                "hooks.kubevirt.io/hookSidecars": '[{"image": "kubevirt/example-hook-sidecar:v0.13.3"}]',
                "smbios.vm.kubevirt.io/baseBoardManufacturer": "Radical Edward",
            },
            'labels': {'special': VM_NAME},
        },
        "cloud_init": CLOUD_INIT,
    },
}
