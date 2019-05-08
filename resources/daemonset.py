import logging

import kubernetes
from openshift.dynamic.exceptions import NotFoundError

from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


class DaemonSet(NamespacedResource):
    """
    DaemonSet object.
    """
    api_version = 'extensions/v1beta1'
    kind = 'DaemonSet'

    def wait_until_deployed(self, timeout=TIMEOUT):
        """
        Wait until all Pods are deployed and ready.

        Args:
            timeout (int): Time to wait for the Daemonset.

        Returns:
            bool: True if all the pods are deployed, False if timeout reached.
        """
        LOGGER.info(f"Wait for {self.kind} {self.name} to deploy all desired pods")
        resources = self.api()
        for rsc in resources.watch(
            namespace=self.namespace,
            timeout=timeout,
            field_selector=f"metadata.name=={self.name}"
        ):
            if (rsc['raw_object']['status'].get('desiredNumberScheduled') ==
                    rsc['raw_object']['status'].get('numberReady')):
                return True
        return False

    def delete(self, wait=False):
        """
        Delete Daemonset

        Args:
            wait (bool): True to wait for Daemonset to be deleted.

        Returns:
            bool: True if delete succeeded, False otherwise.
        """
        try:
            res = self.api().delete(
                name=self.name,
                namespace=self.namespace,
                body=kubernetes.client.V1DeleteOptions(propagation_policy='Foreground'))
        except NotFoundError:
            return False

        LOGGER.info(f"Delete {self.name}")
        if wait and res:
            return self.wait_deleted()
        return res
