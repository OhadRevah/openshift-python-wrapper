import json

from .resource import NamespacedResource


def get_resource_name(bridge_name):
    return f"bridge.network.kubevirt.io/{bridge_name}"


class NetworkAttachmentDefinition(NamespacedResource):
    """
    NetworkAttachmentDefinition object.
    """

    api_group = "k8s.cni.cncf.io"
    resource_name = None

    def wait_for_status(
        self, status, timeout=None, label_selector=None, resource_version=None
    ):
        raise NotImplementedError(f"{self.kind} does not have status")

    def _to_dict(self):
        res = super()._to_dict()
        if self.resource_name is not None:
            res["metadata"]["annotations"] = {
                "k8s.v1.cni.cncf.io/resourceName": self.resource_name
            }
        res["spec"] = {}
        return res


class BridgeNetworkAttachmentDefinition(NetworkAttachmentDefinition):
    def __init__(
        self,
        name,
        namespace,
        bridge_name,
        cni_type="cnv-bridge",
        vlan=None,
        client=None,
        tuning_type=None,
        mtu=None,
    ):
        super().__init__(name=name, namespace=namespace, client=client)
        self._bridge_name = bridge_name
        self._cni_type = cni_type
        self._vlan = vlan
        self._tuning_type = tuning_type
        self._mtu = mtu

    @property
    def resource_name(self):
        return get_resource_name(self._bridge_name)

    def _to_dict(self):
        res = super()._to_dict()
        spec_config = {"cniVersion": "0.3.1"}
        bridge_dict = {"type": self._cni_type, "bridge": self._bridge_name}
        if self._tuning_type:
            spec_config.update({"plugins": [bridge_dict]})
            tuning_dict = {"type": self._tuning_type}
            if self._mtu:
                tuning_dict.update({"mtu": self._mtu})
            spec_config["plugins"].append(tuning_dict)
        else:
            spec_config.update(bridge_dict)
        if self._vlan:
            spec_config["vlan"] = self._vlan

        res["spec"]["config"] = json.dumps(spec_config)
        return res
