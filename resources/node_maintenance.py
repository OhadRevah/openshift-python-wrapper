from .resource import Resource


class NodeMaintenance(Resource):
    """
    Node Maintenance object, inherited from Resource.
    """

    api_group = "kubevirt.io"

    def __init__(self, name, node=None, reason="TEST Reason"):
        super().__init__(name)
        self.node = node
        self.reason = reason

    def _to_dict(self):
        assert self.node, "node is mandatory for create"
        res = super()._to_dict()
        res["spec"] = {"nodeName": self.node.name, "reason": self.reason}
        return res
