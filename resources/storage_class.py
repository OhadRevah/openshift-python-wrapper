from .resource import Resource


class StorageClass(Resource):
    """
    StorageClass object.
    """

    api_group = "storage.k8s.io"

    class Types:
        LOCAL = "local-sc"
        HOSTPATH = "kubevirt-hostpath-provisioner"
        ROOK = "rook-ceph-block"
