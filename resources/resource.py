import logging

import kubernetes
import urllib3
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from urllib3.exceptions import ProtocolError

from distutils.version import Version
import re

from resources.utils import TimeoutExpiredError, nudge_delete
from . import utils

LOGGER = logging.getLogger(__name__)
TIMEOUT = 240
MAX_SUPPORTED_API_VERSION = "v1"


def _find_supported_resource(dyn_client, api_group, kind):
    results = dyn_client.resources.search(group=api_group, kind=kind)
    sorted_results = sorted(
        results, key=lambda result: KubeAPIVersion(result.api_version), reverse=True
    )
    for result in sorted_results:
        if KubeAPIVersion(result.api_version) <= KubeAPIVersion(
            MAX_SUPPORTED_API_VERSION
        ):
            return result


class KubeAPIVersion(Version):
    """
    Implement the Kubernetes API versioning scheme from
    https://kubernetes.io/docs/concepts/overview/kubernetes-api/#api-versioning
    """

    component_re = re.compile(r"(\d+ | [a-z]+)", re.VERBOSE)

    def __init__(self, vstring=None):
        self.vstring = vstring
        self.version = None
        super().__init__(vstring)

    def parse(self, vstring):
        components = [x for x in self.component_re.split(vstring) if x]
        for i, obj in enumerate(components):
            try:
                components[i] = int(obj)
            except ValueError:
                pass

        errmsg = "version '{0}' does not conform to kubernetes api versioning guidelines".format(
            vstring
        )

        if (
            len(components) not in (2, 4)
            or components[0] != "v"
            or not isinstance(components[1], int)
        ):
            raise ValueError(errmsg)
        if len(components) == 4 and (
            components[2] not in ("alpha", "beta") or not isinstance(components[3], int)
        ):
            raise ValueError(errmsg)

        self.version = components

    def __str__(self):
        return self.vstring

    def __repr__(self):
        return "KubeAPIVersion ('{0}')".format(str(self))

    def _cmp(self, other):
        if isinstance(other, str):
            other = KubeAPIVersion(other)

        myver = self.version
        otherver = other.version

        for ver in myver, otherver:
            if len(ver) == 2:
                ver.extend(["zeta", 9999])

        if myver == otherver:
            return 0
        if myver < otherver:
            return -1
        if myver > otherver:
            return 1


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

    api_group = None
    api_version = None
    singular_name = None

    def __init__(self, name, client=None):
        """
        Create a API resource

        Args:
            name (str): Resource name
        """
        if not self.api_group and not self.api_version:
            raise NotImplementedError(
                "Subclasses of Resource require self.api_group or self.api_version to be defined"
            )
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
        if not self.api_version:
            res = _find_supported_resource(self.client, self.api_group, self.kind)
            if not res:
                LOGGER.error(f"Couldn't find {self.kind} in {self.api_group} api group")
                raise
            self.api_version = res.group_version

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

    def wait_for_status(self, status, timeout=TIMEOUT, stop_status="Failed"):
        """
        Wait for resource to be in status

        Args:
            status (str): Expected status.
            timeout (int): Time to wait for the resource.
            stop_status (str): Status which should stop the wait and failed.

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
            namespace=self.namespace,
        )
        final_status = None
        try:
            for sample in samples:
                if sample.items:
                    sample_status = sample.items[0].status
                    if sample_status:
                        final_status = sample_status.phase
                        if sample_status.phase == status:
                            return

                        if sample_status.phase == stop_status:
                            break

        except TimeoutExpiredError:
            if final_status:
                LOGGER.error(f"Status of {self.kind} {self.name} is {final_status}")
            raise

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
        data = self._to_dict()
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

        LOGGER.info(f"Create {self.kind} {self.name}")
        if wait and res:
            return self.wait()
        return res

    @classmethod
    def delete_from_dict(cls, dyn_client, data, namespace=None, wait=False):
        """
        Delete resource represented by the passed data

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster.
            data (dict): Dict representation of resource payload.
            namespace (str): Namespace of the resource unless specified in the supplied yaml.
            wait (bool) : True to wait for resource till deleted.

        Returns:
            True if delete succeeded, False otherwise.
        """

        def _exists(name, namespace):
            try:
                return client.get(name=name, namespace=namespace)
            except NotFoundError:
                return

        def _sampler(name, namespace, force=False):
            samples = utils.TimeoutSampler(
                timeout=TIMEOUT, sleep=1, func=_exists, name=name, namespace=namespace
            )
            for sample in samples:
                if force:
                    nudge_delete(name)
                if not sample:
                    return

        kind = data["kind"]
        name = data["metadata"]["name"]
        namespace = data["metadata"].get("namespace", namespace)
        client = dyn_client.resources.get(api_version=data["apiVersion"], kind=kind)
        LOGGER.info(f"Delete {data['kind']} {name}")
        res = client.delete(name=name, namespace=namespace)
        if wait and res:
            return _sampler(name, namespace, force=kind == "Namespace")
        return res

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
        if not cls.api_version:
            res = _find_supported_resource(dyn_client, cls.api_group, cls.kind)
            if not res:
                LOGGER.error(f"Couldn't find {cls.kind} in {cls.api_group} api group")
                raise
            cls.api_version = res.group_version

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
