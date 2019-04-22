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

    def search(self, regex):
        """
        Search for NetworkAttachmentDefinition

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: NetworkAttachmentDefinition or None
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        if res:
            return NetworkAttachmentDefinition(
                name=res[0],
                namespace=self.namespace,
            )
        return None
