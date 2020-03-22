from contextlib import contextmanager

from resources.datavolume import DataVolume
from utilities.infra import get_images_external_http_server, get_images_https_server


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


def data_volume(
    namespace,
    storage_class_matrix,
    schedulable_nodes=None,
    request=None,
    os_matrix=None,
):
    """ DV creation using create_dv.

    The call to this function can be triggered by calling either
    data_volume_scope_function or data_volume_scope_class fixtures.
    """
    # Extract the key from storage_class_matrix (dict)
    storage_class = [*storage_class_matrix][0]
    # DV name and image path are the only mandatory values
    # Either use request.param or os_matrix
    params_dict = request.param if request else {}

    # Set dv attributes
    # Values can be extracted from request.param or from rhel_os_matrix /
    # windows_os_matrix (passed as os_matrix)
    if os_matrix:
        os_matrix_key = [*os_matrix][0]
        image = os_matrix[os_matrix_key]["image"]
        dv_name = os_matrix_key
    else:
        image = f"{request.param['image']}"
        dv_name = request.param["dv_name"].replace(".", "-").lower()
    source = params_dict.get("source", "http")
    dv_kwargs = {
        "dv_name": dv_name,
        "namespace": namespace.name,
        "source": source,
        "size": params_dict.get("dv_size", "38Gi" if "win" in image else "25Gi"),
        "storage_class": params_dict.get("storage_class", storage_class),
        "access_modes": params_dict.get(
            "access_modes", storage_class_matrix[storage_class]["access_mode"]
        ),
        "volume_mode": params_dict.get(
            "volume_mode", storage_class_matrix[storage_class]["volume_mode"],
        ),
        "content_type": DataVolume.ContentType.KUBEVIRT,
        # In hpp, volume must reside on the same worker as the VM
        "hostpath_node": schedulable_nodes[0].name
        if storage_class == "hostpath-provisioner"
        else None,
    }
    if source == "http":
        dv_kwargs["url"] = f"{get_images_external_http_server()}{image}"
    elif source == "https":
        dv_kwargs["url"] = f"{get_images_https_server()}{image}"

    # Create dv
    with create_dv(**{k: v for k, v in dv_kwargs.items() if v is not None}) as dv:
        dv.wait(timeout=2400 if "win" in image else 1200)
        yield dv
