from .resource import Resource


class Namespace(Resource):
    """
    Namespace object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'Namespace'

    class Status:
        ACTIVE = 'Active'

    def __init__(self, name):
        super(Namespace, self).__init__(name=name)

    def search(self, regex):
        """
        Search for Namespace

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: Namespace or None
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        return Namespace(name=res[0]) if res else None
