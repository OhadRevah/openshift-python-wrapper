from .resource import Resource


class Node(Resource):
    """
    Node object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'Node'

    def __init__(self, name=None):
        super(Node, self).__init__(name=name)

    def search(self, regex):
        """
        Search for Node

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: Node or None
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        return Node(name=res[0]) if res else None
