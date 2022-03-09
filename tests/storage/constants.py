from ocp_resources.storage_class import StorageClass

from utilities.constants import Images
from utilities.storage import HppCsiStorageClass


DV_PARAMS = {
    "dv_name": "source-dv",
    "source": "http",
    "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
    "dv_size": "500Mi",
}
NAMESPACE_PARAMS = {"use_unprivileged_client": False}
CDI_SECRETS = [
    "cdi-apiserver-server-cert",
    "cdi-apiserver-signer",
    "cdi-uploadproxy-server-cert",
    "cdi-uploadproxy-signer",
    "cdi-uploadserver-client-cert",
    "cdi-uploadserver-client-signer",
    "cdi-uploadserver-signer",
]

HPP_STORAGE_CLASSES = [
    StorageClass.Types.HOSTPATH,
    HppCsiStorageClass.Name.HOSTPATH_CSI_LEGACY,
    HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
    HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK,
]
