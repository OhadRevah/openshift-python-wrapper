from pytest_testconfig import config as py_config

from .resource import NamespacedResource


class SriovNetwork(NamespacedResource):
    """
    SriovNetwork object.
    """

    api_group = "sriovnetwork.openshift.io"

    def __init__(
        self,
        name,
        resource_name,
        network_namespace,
        vlan=None,
        ipam=None,
        teardown=True,
    ):
        super().__init__(
            name=name, namespace=py_config["sriov_namespace"], teardown=teardown
        )
        self.network_namespace = network_namespace
        self.resource_name = resource_name
        self.vlan = vlan
        self.ipam = ipam

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {
            "ipam": self.ipam or "{}\n",
            "networkNamespace": self.network_namespace,
            "resourceName": self.resource_name,
        }
        if self.vlan:
            res["spec"]["vlan"] = self.vlan
        return res
