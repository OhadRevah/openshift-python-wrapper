from .resource import NamespacedResource


class ConfigMap(NamespacedResource):
    """
    ConfigMap object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'ConfigMap'
