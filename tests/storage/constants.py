from utilities.constants import Images


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
