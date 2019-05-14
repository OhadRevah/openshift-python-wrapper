from .resource import Resource


class Namespace(Resource):
    """
    Namespace object, inherited from Resource.
    """
    api_version = 'v1'
    kind = 'Namespace'

    class Status:
        ACTIVE = 'Active'
