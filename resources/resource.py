import logging

import kubernetes
import urllib3
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from urllib3.exceptions import ProtocolError

from . import utils

LOGGER = logging.getLogger(__name__)
TIMEOUT = 240


class classproperty(object):  # noqa: N801
    def __init__(self, func):
        self.func = func

    def __get__(self, obj, owner):
        return self.func(owner)


class ValueMismatch(Exception):
    """
    Raises when value doesn't match the class value
    """

    pass


class Resource(object):
    """
    Base class for API resources
    """

    api_version = None
    singular_name = None

    def __init__(self, name, client=None):
        """
        Create a API resource

        Args:
            name (str): Resource name
        """
        self.namespace = None
        self.name = name
        self.client = client
        if not self.client:
            try:
                self.client = DynamicClient(kubernetes.config.new_client_from_config())
            except (
                kubernetes.config.ConfigException,
                urllib3.exceptions.MaxRetryError,
            ):
                LOGGER.error(
                    "You need to be logged into a cluster or have $KUBECONFIG env configured"
                )
                raise

    @classproperty
    def kind(cls):  # noqa: N805
        # return the name of the last class in MRO list that is not one of base
        # classes; otherwise return None
        for c in reversed(
            list(
                c
                for c in cls.mro()
                if c not in NamespacedResource.mro() and issubclass(c, Resource)
            )
        ):
            return c.__name__

    def _base_body(self):
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": {"name": self.name},
        }

    def _to_dict(self):
        """
        Generate intended dict representation of the resource.
        """
        return self._base_body()

    def __enter__(self):
        data = self._to_dict()
        LOGGER.info(f"Posting {data}")
        self.create_from_dict(
            dyn_client=self.client, data=data, namespace=self.namespace
        )
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        data = self._to_dict()
        LOGGER.info(f"Deleting {data}")
        self.delete(wait=True)

    def api(self, **kwargs):
        """
        Get resource API

        Keyword Args:
            pretty
            _continue
            include_uninitialized
            field_selector
            label_selector
            limit
            resource_version
            timeout_seconds
            watch
            async_req

        Returns:
            Resource: Resource object.
        """
        if self.singular_name:
            kwargs["singular_name"] = self.singular_name
        return self.client.resources.get(
            api_version=self.api_version, kind=self.kind, **kwargs
        )

    def wait(self, timeout=TIMEOUT):
        """
        Wait for resource

        Args:
            timeout (int): Time to wait for the resource.

        Raises:
            TimeoutExpiredError: If resource not exists.
        """

        def _exists():
            return self.instance

        LOGGER.info(f"Wait until {self.kind} {self.name} is created")
        samples = utils.TimeoutSampler(
            timeout=timeout,
            sleep=1,
            exceptions=(ProtocolError, NotFoundError),
            func=_exists,
        )
        for sample in samples:
            if sample:
                return

    def wait_deleted(self, timeout=TIMEOUT):
        """
        Wait until resource is deleted

        Args:
            timeout (int): Time to wait for the resource.

        Returns:
            bool: True if resource is gone, False if timeout reached.
        """
        LOGGER.info(f"Wait until {self.kind} {self.name} is deleted")
        return self._client_wait_deleted(timeout)

    def nudge_delete(self):
        """
        Resource specific "nudge delete" action that may help the resource to
        complete its cleanup. Needed by some resources.
        """

    def _client_wait_deleted(self, timeout):
        """
        client-side Wait until resource is deleted

        Args:
            timeout (int): Time to wait for the resource.

        Raises:
            TimeoutExpiredError: If resource still exists.
        """

        def _exists():
            """
            Whether self exists on the server
            """
            try:
                return self.instance
            except NotFoundError:
                return None

        samples = utils.TimeoutSampler(timeout=timeout, sleep=1, func=_exists)
        for sample in samples:
            self.nudge_delete()
            if not sample:
                return

    def wait_for_status(self, status, timeout=TIMEOUT):
        """
        Wait for resource to be in status

        Args:
            status (str): Expected status.
            timeout (int): Time to wait for the resource.

        Raises:
            TimeoutExpiredError: If resource in not in desire status.
        """
        LOGGER.info(f"Wait for {self.kind} {self.name} status to be {status}")
        samples = utils.TimeoutSampler(
            timeout=timeout,
            sleep=1,
            exceptions=ProtocolError,
            func=self.api().get,
            field_selector=f"metadata.name=={self.name}",
        )
        for sample in samples:
            if sample.items:
                sample_status = sample.items[0].status
                if sample_status:
                    if sample_status.phase == status:
                        return

    @classmethod
    def create_from_dict(cls, dyn_client, data, namespace=None):
        """
        Create resource from given yaml file.

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster.
            data (dict): Dict representing the resource.
            namespace (str): Namespace of the resource unless specified in the supplied yaml.
        """
        client = dyn_client.resources.get(
            api_version=data["apiVersion"], kind=data["kind"]
        )
        LOGGER.info(f"Create {data['kind']} {data['metadata']['name']}")
        return client.create(
            body=data, namespace=data["metadata"].get("namespace", namespace)
        )

    def create(self, body=None, wait=False):
        """
        Create resource.

        Args:
            body (dict): Resource data to create.
            wait (bool) : True to wait for resource status.

        Returns:
            bool: True if create succeeded, False otherwise.

        Raises:
            ValueMismatch: When body value doesn't match class value
        """
        data = self._base_body()
        if body:
            kind = body["kind"]
            name = body.get("name")
            api_version = body["apiVersion"]
            if kind != self.kind:
                ValueMismatch(f"{kind} != {self.kind}")
            if name and name != self.name:
                ValueMismatch(f"{name} != {self.name}")
            if api_version != self.api_version:
                ValueMismatch(f"{api_version} != {self.api_version}")

            data.update(body)
        res = self.api().create(body=data, namespace=self.namespace)

        LOGGER.info(f"Create {kind} {self.name}")
        if wait and res:
            return self.wait()
        return res

    @classmethod
    def delete_from_dict(cls, dyn_client, data, namespace=None):
        """
        Delete resource represented by the passed data

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster.
            data (dict): Dict representation of resource payload.
            namespace (str): Namespace of the resource unless specified in the supplied yaml.

        Returns:
            True if delete succeeded, False otherwise.
        """
        name = data["metadata"]["name"]
        client = dyn_client.resources.get(
            api_version=data["apiVersion"], kind=data["kind"]
        )
        LOGGER.info(f"Delete {data['kind']} {name}")
        return client.delete(
            name=name, namespace=data["metadata"].get("namespace", namespace)
        )

    def delete(self, wait=False):
        resource_list = self.api()
        try:
            res = resource_list.delete(name=self.name, namespace=self.namespace)
        except NotFoundError:
            return False

        LOGGER.info(f"Delete {self.kind} {self.name}")
        if wait and res:
            return self.wait_deleted()
        return res

    @property
    def status(self):
        """
        Get resource status

        Status: Running, Scheduling, Pending, Unknown, CrashLoopBackOff

        Returns:
           str: Status
        """
        LOGGER.info(f"Get {self.kind} {self.name} status")
        return self.instance.status.phase

    def update(self, resource_dict):
        """
        Update resource with resource dict

        Args:
            resource_dict: Resource dictionary
        """
        LOGGER.info(f"Update {self.kind} {self.name}")
        self.api().patch(
            body=resource_dict,
            namespace=self.namespace,
            content_type="application/merge-patch+json",
        )

    @classmethod
    def get(cls, dyn_client, singular_name=None, *args, **kwargs):
        """
        Get resources

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster
            singular_name (str): Resource kind (in lowercase), in use where we have multiple matches for resource

        Returns:
            generator: Generator of Resources of cls.kind
        """
        get_kwargs = {"singular_name": "singular_name"} if singular_name else {}
        for resource_field in (
            dyn_client.resources.get(
                kind=cls.kind, api_version=cls.api_version, **get_kwargs
            )
            .get(*args, **kwargs)
            .items
        ):
            yield cls(name=resource_field.metadata.name)

    @property
    def instance(self):
        """
        Get resource instance

        Returns:
            openshift.dynamic.client.ResourceInstance
        """
        return self.api().get(name=self.name)

    @property
    def labels(self):
        """
        Method to get dict of labels for this resource

        Returns:
           labels(dict): dict labels
        """
        return self.instance["metadata"]["labels"]


class NamespacedResource(Resource):
    """
    Namespaced object, inherited from Resource.
    """

    def __init__(self, name, namespace, client=None):
        super().__init__(name=name, client=client)
        self.namespace = namespace

    @classmethod
    def get(cls, dyn_client, singular_name=None, *args, **kwargs):
        """
        Get resources

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster
            singular_name (str): Resource kind (in lowercase), in use where we have multiple matches for resource


        Returns:
            generator: Generator of Resources of cls.kind
        """
        get_kwargs = {"singular_name": singular_name} if singular_name else {}
        for resource_field in (
            dyn_client.resources.get(
                kind=cls.kind, api_version=cls.api_version, **get_kwargs
            )
            .get(*args, **kwargs)
            .items
        ):
            yield cls(
                name=resource_field.metadata.name,
                namespace=resource_field.metadata.namespace,
            )

    @property
    def instance(self):
        """
        Get resource instance

        Returns:
            openshift.dynamic.client.ResourceInstance
        """
        return self.api().get(name=self.name, namespace=self.namespace)
