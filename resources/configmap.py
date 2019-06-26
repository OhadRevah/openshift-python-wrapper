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

    def _base_body(self):
        body = super()._base_body()
        body.update({
            "data": {
                "tlsregistry.crt": self.data,
            }
        })
        return body
