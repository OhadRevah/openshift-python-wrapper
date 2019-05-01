from .resource import NamespacedResource


class NameSpace(NamespacedResource):
    """
    NameSpace object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'Namespace'

    class Status:
        ACTIVE = 'Active'

    def __init__(self, name):
        super(NameSpace, self).__init__(name=name, namespace=name)

    def search(self, regex):
        """
        Search for NameSpace

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: NameSpace or None
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        return NameSpace(name=res[0]) if res else None
