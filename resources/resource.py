import logging

import kubernetes
import urllib3
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError

from . import utils

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


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

    try:
        client = DynamicClient(kubernetes.config.new_client_from_config())
    except (kubernetes.config.ConfigException, urllib3.exceptions.MaxRetryError):
        LOGGER.error('You need to be logged into a cluster or have $KUBECONFIG env configured')
        raise

    def __init__(self, name):
        """
        Create a API resource

        Args:
            name (str): Resource name
        """
        self.namespace = None
        self.name = name

    @classproperty
    def kind(cls):  # noqa: N805
        # return the name of the last class in MRO list that is not one of base
        # classes; otherwise return None
        for c in reversed(
            list(c for c in cls.mro() if c not in NamespacedResource.mro())
        ):
            return c.__name__

    def _base_body(self):
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": {
                "name": self.name,
            },
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
            dyn_client=self.client, data=data, namespace=self.namespace)
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
        return self.client.resources.get(api_version=self.api_version, kind=self.kind, **kwargs)

    def wait(self, timeout=TIMEOUT, label_selector=None, resource_version=None):
        """
        Wait for resource

        Args:
            timeout (int): Time to wait for the resource.
            label_selector (str): The label selector with which to filter results
            resource_version (str): The version with which to filter results. Only events with
                a resource_version greater than this value will be returned

        Returns:
            bool: True if resource exists, False if timeout reached.
        """
        LOGGER.info(f"Wait until {self.kind} {self.name} is created")
        for rsc in self.api().watch(
            namespace=self.namespace,
            timeout=timeout,
            resource_version=resource_version,
            label_selector=label_selector,
            field_selector=f"metadata.name=={self.name}"
        ):
            if rsc['type'] == 'ADDED':
                return True
        return False

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

        Returns:
            bool: True if resource is gone, False if timeout reached.
        """
        def _exists():
            """
            Whether self exists on the server

            Returns:
                bool: True if the resource was found, False if not
            """
            try:
                return self.instance
            except NotFoundError:
                return None

        samples = utils.TimeoutSampler(timeout=timeout, sleep=1, func=_exists)
        for sample in samples:
            self.nudge_delete()
            if not sample:
                return True
        return False

    def wait_for_status(self, status, timeout=TIMEOUT, label_selector=None, resource_version=None):
        """
        Wait for resource to be in status

        Args:
            status (str): Expected status.
            timeout (int): Time to wait for the resource.
            label_selector (str): The label selector with which to filter results
            resource_version (str): The version with which to filter results. Only events with
                a resource_version greater than this value will be returned

        Returns:
            bool: True if resource in desire status, False if timeout reached.
        """
        LOGGER.info(f"Wait for {self.kind} {self.name} status to be {status}")
        resources = self.api()
        for rsc in resources.watch(
            namespace=self.namespace,
            timeout=timeout,
            label_selector=label_selector,
            resource_version=resource_version,
            field_selector=f"metadata.name=={self.name}"
        ):
            if 'status' in rsc['raw_object'] and rsc['raw_object']['status'].get('phase') == status:
                return True
        return False

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
            api_version=data['apiVersion'], kind=data['kind']
        )
        LOGGER.info(f"Create {data['kind']} {data['metadata']['name']}")
        return client.create(
            body=data, namespace=data['metadata'].get('namespace', namespace)
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
            kind = body['kind']
            name = body.get('name')
            api_version = body['apiVersion']
            if kind != self.kind:
                ValueMismatch(f'{kind} != {self.kind}')
            if name and name != self.name:
                ValueMismatch(f'{name} != {self.name}')
            if api_version != self.api_version:
                ValueMismatch(f'{api_version} != {self.api_version}')

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
        name = data['metadata']['name']
        client = dyn_client.resources.get(api_version=data['apiVersion'], kind=data['kind'])
        LOGGER.info(f"Delete {data['kind']} {name}")
        return client.delete(
            name=name, namespace=data['metadata'].get('namespace', namespace)
        )

    def delete(self, wait=False):
        """
        Delete resource

        Args:
            wait (bool): True to wait for pod to be deleted.

        Returns:
            True if delete succeeded, False otherwise.
        """
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
        self.api().replace(body=resource_dict, namespace=self.namespace)

    @classmethod
    def get(cls, dyn_client, *args, **kwargs):
        """
        Get resources

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster

        Returns:
            generator: Generator of Resources of cls.kind
        """
        for resource_field in dyn_client.resources.get(
                kind=cls.kind, api_version=cls.api_version).get(*args, **kwargs).items:
            yield cls(name=resource_field.metadata.name)

    @property
    def instance(self):
        """
        Get resource instance

        Returns:
            openshift.dynamic.client.ResourceInstance
        """
        return self.api().get(name=self.name)


class NamespacedResource(Resource):
    """
    Namespaced object, inherited from Resource.
    """
    def __init__(self, name, namespace):
        super().__init__(name=name)
        self.namespace = namespace

    @classmethod
    def get(cls, dyn_client, *args, **kwargs):
        """
        Get resources

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster

        Returns:
            generator: Generator of Resources of cls.kind
        """
        for resource_field in dyn_client.resources.get(
                kind=cls.kind, api_version=cls.api_version).get(*args, **kwargs).items:
            yield cls(
                name=resource_field.metadata.name, namespace=resource_field.metadata.namespace
            )

    @property
    def instance(self):
        """
        Get resource instance

        Returns:
            openshift.dynamic.client.ResourceInstance
        """
        return self.api().get(name=self.name, namespace=self.namespace)
