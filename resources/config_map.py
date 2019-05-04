from .resource import NamespacedResource


class ConfigMap(NamespacedResource):
    """
    ConfigMap object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'ConfigMap'

    def __init__(self, name, namespace):
        super(ConfigMap, self).__init__(name=name, namespace=namespace)
