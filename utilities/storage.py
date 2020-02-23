from contextlib import contextmanager

from resources.datavolume import DataVolume
from utilities.infra import get_images_external_http_server


@contextmanager
def create_dv(
    dv_name,
    namespace,
    storage_class,
    volume_mode,
    url=None,
    source="http",
    content_type=DataVolume.ContentType.KUBEVIRT,
    size="5Gi",
    secret=None,
    cert_configmap=None,
    hostpath_node=None,
    access_modes=DataVolume.AccessMode.RWO,
    client=None,
    source_pvc=None,
    source_namespace=None,
):
    with DataVolume(
        source=source,
        name=dv_name,
        namespace=namespace,
        url=url,
        content_type=content_type,
        size=size,
        storage_class=storage_class,
        cert_configmap=cert_configmap,
        volume_mode=volume_mode,
        hostpath_node=hostpath_node,
        access_modes=access_modes,
        secret=secret,
        client=client,
        source_pvc=source_pvc,
        source_namespace=source_namespace,
    ) as dv:
        yield dv


def data_volume(request, namespace, storage_class_matrix, schedulable_nodes=None):
    """ DV creation using create_dv.

    The call to this function can be triggered by calling either
    data_volume_scope_function or data_volume_scope_class fixtures.
    """
    # Extract the key from storage_class_matrix (dict)
    storage_class = [*storage_class_matrix][0]

    # Set dv attributes
    dv_kwargs = {
        "dv_name": request.param["dv_name"].replace(".", "-").lower(),
        "namespace": namespace.name,
        "source": request.param.get("source", "http"),
        "url": f"{get_images_external_http_server()}{request.param['image']}",
        "size": request.param.get(
            "dv_size", "35Gi" if "win" in request.param["dv_name"] else "25Gi"
        ),
        "storage_class": request.param.get("storage_class", storage_class),
        "access_modes": request.param.get(
            "access_modes", storage_class_matrix[storage_class]["access_mode"]
        ),
        "volume_mode": request.param.get(
            "volume_mode", storage_class_matrix[storage_class]["volume_mode"],
        ),
        "content_type": DataVolume.ContentType.KUBEVIRT,
        # In hpp, volume must reside on the same worker as the VM
        "hostpath_node": schedulable_nodes[0].name
        if storage_class == "hostpath-provisioner"
        else None,
    }

    # Create dv
    with create_dv(**{k: v for k, v in dv_kwargs.items() if v is not None}) as dv:
        dv.wait(timeout=1800 if "win" in request.param["dv_name"] else 1200)
        yield dv
