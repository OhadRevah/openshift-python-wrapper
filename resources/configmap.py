from .resource import NamespacedResource


class ConfigMap(NamespacedResource):
    """
    Configmap object
    """
    api_version = 'v1'

    def __init__(
            self, name, namespace, data=None):
        super().__init__(name=name, namespace=namespace)
        self.data = data

    def _to_dict(self):
        res = super()._base_body()
        res.update({
            "data": {
                "tlsregistry.crt": self.data,
            }
        })
        return res
