from .resource import NamespacedResource


class Secret(NamespacedResource):
    """
    Secret object.
    """

    api_version = "v1"

    def __init__(
        self,
        name,
        namespace,
        accesskeyid=None,
        secretkey=None,
        htpasswd=None,
        teardown=True,
    ):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self.accesskeyid = accesskeyid
        self.secretkey = secretkey
        self.htpasswd = htpasswd

    def to_dict(self):
        res = super()._base_body()
        if self.accesskeyid:
            res.update(
                {"data": {"accessKeyId": self.accesskeyid, "secretKey": self.secretkey}}
            )
        if self.htpasswd:
            res.update({"data": {"htpasswd": self.htpasswd}})
        return res
