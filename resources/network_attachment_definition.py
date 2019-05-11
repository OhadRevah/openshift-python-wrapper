import json

from .resource import NamespacedResource


def get_resource_name(bridge_name):
    return f"bridge.network.kubevirt.io/{bridge_name}"


class NetworkAttachmentDefinition(NamespacedResource):
    """
    NetworkAttachmentDefinition object.
    """
    api_version = 'k8s.cni.cncf.io/v1'
    resource_name = None

    def wait_for_status(self, status, timeout=None, label_selector=None, resource_version=None):
        raise NotImplementedError(f"{self.kind} does not have status")

    def _to_dict(self):
        res = super()._to_dict()
        if self.resource_name is not None:
            res["metadata"]["annotations"] = {
                "k8s.v1.cni.cncf.io/resourceName": self.resource_name,
            }
        res["spec"] = {}
        return res


class BridgeNetworkAttachmentDefinition(NetworkAttachmentDefinition):
    def __init__(self, name, namespace, bridge_name, cni_type="cnv-bridge"):
        super().__init__(name, namespace)
        self._bridge_name = bridge_name
        self._cni_type = cni_type

    @property
    def resource_name(self):
        return get_resource_name(self._bridge_name)

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"]["config"] = json.dumps({
            "cniVersion": "0.3.1",
            "type": self._cni_type,
            "bridge": self._bridge_name,
        })
        return res
