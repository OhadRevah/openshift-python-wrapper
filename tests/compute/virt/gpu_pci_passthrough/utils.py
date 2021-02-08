from resources.resource import ResourceEditor

from utilities.constants import GPU_DEVICE_NAME


def update_vm_to_gpus_spec(vm):
    vm_dict = vm.instance.to_dict()
    vm_spec_dict = vm_dict["spec"]["template"]["spec"]
    vm_spec_dict["domain"]["devices"].pop("hostDevices", "No key Found")
    ResourceEditor(patches={vm: vm_dict}, action="replace").update()
    ResourceEditor(
        patches={
            vm: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {
                                    "gpus": [
                                        {
                                            "deviceName": GPU_DEVICE_NAME,
                                            "name": "gpus",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
        }
    ).update()
