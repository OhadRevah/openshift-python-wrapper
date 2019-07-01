import logging

from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)


class UploadTokenRequest(NamespacedResource):
    """
    OpenShift UploadTokenRequest object.
    """

    api_version = "upload.cdi.kubevirt.io/v1alpha1"

    def _to_dict(self):
        res = super()._base_body()
        res.update({"spec": {"pvcName": self.name}})
        return res
