import logging

import kubernetes
import urllib3
import yaml
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from . import utils

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


class Resource(object):
    """
    DynamicClient Resource class
    """
    api_version = None
    kind = None

    def __init__(self, name):
        """
        Create DynamicClient

        Args:
            name (str): Resource name
        """
        try:
            self.client = DynamicClient(kubernetes.config.new_client_from_config())
        except (kubernetes.config.ConfigException, urllib3.exceptions.MaxRetryError):
            LOGGER.error('You need to be login to cluster or have $KUBECONFIG env configured')
            raise

        self.kube_api = kubernetes.client.CoreV1Api(api_client=self.client.client)
        self.namespace = None
        self.name = name

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
        supported_kind_to_watch = [
            'Pod', 'Namespace', 'ConfigMap', 'Node', 'VirtualMachine', 'VirtualMachineInstance', 'DataVolume',
            'PersistentVolumeClaim',
        ]
        LOGGER.info(f"Wait until {self.kind} {self.name} is deleted")

        if self.kind not in supported_kind_to_watch:
            samples = utils.TimeoutSampler(
                timeout=timeout, sleep=1, func=lambda: bool(self.instance)
            )
            for sample in samples:
                if not sample:
                    return True
            return False

        watcher = kubernetes.watch.Watch()
        for event in watcher.stream(
            func=self.kube_api.list_event_for_all_namespaces, timeout_seconds=timeout,
        ):
            if event['object'].reason == 'SuccessfulDelete':
                event_object = event['object'].involved_object
                if event_object.name == self.name and event_object.namespace == self.namespace:
                    watcher.stop()
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
            if rsc['raw_object']['status'].get('phase') == status:
                return True
        return False

    @classmethod
    def create_from_yaml(cls, dyn_client, yaml_file, namespace=None):
        """
        Create resource from given yaml file.

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster.
            yaml_file (str): Path to yaml file.
            namespace (str): Namespace of the resource unless specified in the supplied yaml.
        """
        with open(yaml_file, 'r') as stream:
            data = yaml.full_load(stream)

        return cls.create_from_dict(
            dyn_client=dyn_client, resource_dict=data, namespace=namespace
        )

    @classmethod
    def create_from_dict(cls, dyn_client, resource_dict, namespace=None):
        """
        Create resource from given yaml file.

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster.
            resource_dict (dict): Path to yaml file.
            namespace (str): Namespace of the resource unless specified in the supplied yaml.
        """
        client = dyn_client.resources.get(
            api_version=resource_dict['apiVersion'], kind=resource_dict['kind']
        )
        LOGGER.info(f"Create {resource_dict['metadata']['name']}")
        return client.create(
            body=resource_dict, namespace=resource_dict['metadata'].get('namespace', namespace)
        )

    def create(self, wait=False):
        """
        Create resource from given yaml file or from dict

        Args:
            wait (bool) : True to wait for resource status.

        Returns:
            bool: True if create succeeded, False otherwise.
        """
        data = {
            'apiVersion': self.api_version,
            'kind': self.kind,
            'metadata': {'name': self.name}
        }
        res = self.api().create(body=data, namespace=self.namespace)

        LOGGER.info(f"Create {self.name}")
        if wait and res:
            return self.wait()
        return res

    @classmethod
    def delete_from_yaml(cls, dyn_client, yaml_file, namespace=None):
        """
        Delete resource from yaml file

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster.
            yaml_file (str): Path to yaml file to delete from yaml.
            namespace (str): Namespace of the resource unless specified in the supplied yaml.

        Returns:
            True if delete succeeded, False otherwise.
        """
        with open(yaml_file, 'r') as stream:
            data = yaml.full_load(stream)

        name = data['metadata']['name']
        client = dyn_client.resources.get(api_version=data['apiVersion'], kind=data['kind'])
        LOGGER.info(f"Delete {name}")
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

        LOGGER.info(f"Delete {self.name}")
        if wait and res:
            return self.wait_deleted()
        return res

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
    def get_resources(cls, dyn_client, *args, **kwargs):
        """
        Get resources

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster

        Returns:
            generator: Generator of Resources of cls.kind
        """
        for resource_field in dyn_client.resources.get(kind=cls.kind).get(*args, **kwargs).items:
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
        super(NamespacedResource, self).__init__(name=name)
        self.namespace = namespace

    @classmethod
    def get_resources(cls, dyn_client, *args, **kwargs):
        """
        Get resources

        Args:
            dyn_client (DynamicClient): Open connection to remote cluster

        Returns:
            generator: Generator of Resources of cls.kind
        """
        for resource_field in dyn_client.resources.get(kind=cls.kind).get(*args, **kwargs).items:
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
