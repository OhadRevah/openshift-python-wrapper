from .resource import Resource


class Node(Resource):
    """
    Node object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'Node'
