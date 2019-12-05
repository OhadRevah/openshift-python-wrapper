# -*- coding: utf-8 -*-

from .resource import Resource


class StorageClass(Resource):
    """
    StorageClass object.
    """

    api_group = "storage.k8s.io"

    class Types:
        """
        These are names of StorageClass instances when you run `oc get sc`
        """

        LOCAL = "local-sc"
        HOSTPATH = "kubevirt-hostpath-provisioner"
        ROOK = "rook-ceph-block"

    class Provisioner:
        HOSTPATH = "kubevirt.io/hostpath-provisioner"
        LOCAL_SC = "kubernetes.io/no-provisioner"
        CEPH_RBD = "rook-ceph.rbd.csi.ceph.com"

    class VolumeBindingMode:
        """
        VolumeBindingMode indicates how PersistentVolumeClaims should be provisioned and bound.
        When unset, Immediate is used.
        When "Immediate", if you want to use the "node aware" hostpath-provisioner,
        ProvisionOnNode annotations should be introduced to PVC.
        Or in order to be able to use the hpp without specifying the node on the PVC,
        since CNV-2.2, hpp supports for "WaitForFirstConsumer".
        """

        Immediate = "Immediate"
        WaitForFirstConsumer = "WaitForFirstConsumer"
