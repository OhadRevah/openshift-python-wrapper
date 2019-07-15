from .resource import NamespacedResource


class Secret(NamespacedResource):
    """
    Secret object
    """

    api_version = "v1"

    def __init__(self, name, namespace, accesskeyid, secretkey):
        super().__init__(name=name, namespace=namespace)
        self.accessKeyId = accesskeyid
        self.secretKey = secretkey

    def _to_dict(self):
        res = super()._base_body()
        res.update(
            {"data": {"accessKeyId": self.accessKeyId, "secretKey": self.secretKey}}
        )
        return res
