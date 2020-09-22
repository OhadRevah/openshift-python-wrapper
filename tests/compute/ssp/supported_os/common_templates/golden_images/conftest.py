import pytest
from resources.datavolume import DataVolume
from tests.conftest import vm_instance_from_template


def _data_volume_template_dict(
    target_dv_name,
    source_dv,
    worker_node,
):
    source_dv_pvc = source_dv.instance.spec.pvc

    data_volume_template_dict = {
        "apiVersion": "cdi.kubevirt.io/v1alpha1",
        "kind": "DataVolume",
        "metadata": {"name": target_dv_name},
        "spec": {
            "pvc": {
                "storageClassName": source_dv_pvc.storageClassName,
                "accessModes": source_dv_pvc.accessModes,
                "volumeMode": source_dv_pvc.volumeMode,
                "resources": {
                    "requests": {"storage": source_dv_pvc.resources.requests.storage},
                },
            },
            "source": {
                "pvc": {
                    "name": source_dv.name,
                    "namespace": source_dv.namespace,
                }
            },
        },
    }

    if DataVolume.AccessMode.RWO in source_dv_pvc.accessModes:
        data_volume_template_dict["metadata"].setdefault("annotations", {})[
            "kubevirt.io/provisionOnNode"
        ] = worker_node.name

    return data_volume_template_dict


@pytest.fixture()
def vm_instance_from_template_golden_image_multi_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    worker_node1,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=_data_volume_template_dict(
            target_dv_name=request.param["target_dv_name"],
            source_dv=data_volume_multi_storage_scope_function,
            worker_node=worker_node1,
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def vm_instance_from_template_golden_image_multi_scope_class(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_class,
    worker_node1,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=_data_volume_template_dict(
            target_dv_name=request.param["target_dv_name"],
            source_dv=data_volume_multi_storage_scope_class,
            worker_node=worker_node1,
        ),
    ) as vm:
        yield vm
