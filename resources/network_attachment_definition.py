from .resource import NamespacedResource


class NetworkAttachmentDefinition(NamespacedResource):
    """
    Node object, inherited from Resource.
    """
    api_version = 'k8s.cni.cncf.io/v1'
    kind = 'NetworkAttachmentDefinition'

    def __init__(self, name=None, namespace=None):
        super(NetworkAttachmentDefinition, self).__init__(name=name, namespace=namespace)

    def wait_for_status(self, status, timeout=None, label_selector=None, resource_version=None):
        raise NotImplementedError(f"{self.kind} does not have status")
