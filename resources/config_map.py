from .resource import NamespacedResource


class ConfigMap(NamespacedResource):
    """
    ConfigMap object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'ConfigMap'

    def __init__(self, name, namespace):
        super(ConfigMap, self).__init__(name=name, namespace=namespace)

    def search(self, regex):
        """
        Search for ConfigMap

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: ConfigMap or None
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        if res:
            return ConfigMap(
                name=res[0],
                namespace=self.namespace,
            )
        return None
