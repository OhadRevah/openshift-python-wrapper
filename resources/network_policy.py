from .resource import NamespacedResource


class NetworkPolicy(NamespacedResource):
    """
    NetworkPolicy object.
    """

    api_version = "networking.k8s.io/v1"
