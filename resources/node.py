from .resource import NamespacedResource, Resource


class Node(Resource):
    """
    Node object, inherited from Resource.
    """

    api_version = "v1"

    class Status(NamespacedResource.Status):
        READY = "Ready"
        SCHEDULING_DISABLED = "Ready,SchedulingDisabled"
