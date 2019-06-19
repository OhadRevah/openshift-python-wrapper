# -*- coding: utf-8 -*-
import logging

from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


class ReplicasExists(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Replicas exists even after replicas in {self.name} spec has been updated to 0"


class Deployment(NamespacedResource):
    """
    OpenShift Deployment object.
    """

    api_version = "extensions/v1beta1"

    def scale_replicas(self, replica_count=int):
        """
        Update replicas in deployment.

        Args:
            replica_count (int): Number of replicas.

        Returns:
            Deployment is updated successfully
        """
        body = super()._to_dict()
        body.update({"spec": {"replicas": replica_count}})

        LOGGER.info(f"Set deployment replicas: {replica_count}")
        return self.update(resource_dict=body)

    def wait_until_no_replicas(self, timeout=TIMEOUT):
        """
        Wait until all replicas are updated.

        Args:
            timeout (int): Time to wait for the deployment.

        Returns:
            bool: True if availableReplicas is not found.
        """
        LOGGER.info(f"Wait for {self.kind} {self.name} to update replicas")
        resources = self.api()
        for rsc in resources.watch(
            namespace=self.namespace,
            timeout=timeout,
            field_selector=f"metadata.name=={self.name}",
        ):
            status = rsc["raw_object"]["status"]
            available_replicas = status.get("availableReplicas")
            if not available_replicas:
                return True
        raise ReplicasExists(name=self.name)

    def wait_until_avail_replicas(self, timeout=TIMEOUT):
        """
        Wait until all replicas are updated.

        Args:
            timeout (int): Time to wait for the deployment.

        Returns:
            bool: True if availableReplicas is equal to replicas.
        """
        LOGGER.info(
            f"Wait for {self.kind} {self.name} to ensure availableReplicas == replicas"
        )
        resources = self.api()
        for rsc in resources.watch(
            namespace=self.namespace,
            timeout=timeout,
            field_selector=f"metadata.name=={self.name}",
        ):
            status = rsc["raw_object"]["status"]
            available_replicas = status.get("availableReplicas")
            replicas = status.get("replicas")
            if replicas == available_replicas:
                return True
        raise ValueError
