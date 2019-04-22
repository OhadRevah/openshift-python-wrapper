import logging

import kubernetes
import urllib3
import yaml
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from . import utils
from utilities import utils as ext_utils

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


class Resource(object):
    """
    DynamicClient Resource class
    """
    api_version = None
    kind = None

    def __init__(self, name=None):
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

    def get(self, **kwargs):
        """
        Get resource

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
            namespace

        Returns:
            ResourceField: ResourceField object.
        """
        LOGGER.info(f"Get {self.kind} {self.name}")
        for resource_field in self.list(**kwargs):
            if resource_field.metadata.name == self.name:
                return resource_field
        return None

    def get_dict(self):
        """
        Get resource as dict

        Returns:
            dict: Resource.
        """
        res = self.api().get(
            namespace=self.namespace, field_selector=f'metadata.name={self.name}'
        ).to_dict()
        return res['items'][0] if res['items'] else {}

    def list(self, **kwargs):
        """
        Get resources

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
            list: ResourceField.
        """
        for resource_field in self.api().get(namespace=self.namespace, **kwargs).items:
            yield resource_field

    def list_names(self, **kwargs):
        """
        Get resources names list

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
            namespace

        Returns:
            list: Resources.
        """
        LOGGER.info(f"Get all {self.kind} names ")
        return [i.metadata.name for i in self.list(**kwargs)]

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
            'Pod', 'NameSpace', 'ConfigMap', 'Node', 'VirtualMachine', 'VirtualMachineInstance'
        ]
        LOGGER.info(f"Wait until {self.kind} {self.name} is deleted")

        if self.kind not in supported_kind_to_watch:
            samples = utils.TimeoutSampler(
                timeout=timeout, sleep=1, func=lambda: bool(self.get())
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

    def create(self, yaml_file=None, resource_dict=None, wait=False):
        """
        Create resource from given yaml file or from dict

        Args:
            yaml_file (str): Path to yaml file.
            resource_dict (dict): Dict to create resource from.
            wait (bool) : True to wait for resource status.

        Returns:
            bool: True if create succeeded, False otherwise.
        """
        if yaml_file:
            with open(yaml_file, 'r') as stream:
                data = yaml.full_load(stream)

            self._extract_data_from_yaml(yaml_data=data)

        else:
            if not resource_dict:
                data = {
                    'apiVersion': self.api_version,
                    'kind': self.kind,
                    'metadata': {'name': self.namespace}
                }
            else:
                data = resource_dict

        res = self.api().create(body=data, namespace=self.namespace)

        LOGGER.info(f"Create {self.name}")
        if wait and res:
            return self.wait()
        return res

    def delete(self, yaml_file=None, wait=False):
        """
        Delete resource

        Args:
            yaml_file (str): Path to yaml file to delete from yaml.
            wait (bool): True to wait for pod to be deleted.

        Returns:
            True if delete succeeded, False otherwise.
        """
        if yaml_file:
            with open(yaml_file, 'r') as stream:
                data = yaml.full_load(stream)

            self._extract_data_from_yaml(yaml_data=data)

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
        return self.get().status.phase

    def _extract_data_from_yaml(self, yaml_data):
        """
        Extract data from yaml stream

        Args:
            yaml_data (dict): Dict from yaml file
        """
        self.namespace = self.namespace or yaml_data['metadata'].get('namespace')
        self.name = yaml_data['metadata']['name']
        self.api_version = yaml_data['apiVersion']
        self.kind = yaml_data['kind']

    def update(self, resource_dict):
        """
        Update resource with resource dict

        Args:
            resource_dict: Resource dictionary
        """
        LOGGER.info(f"Update {self.kind} {self.name}")
        self.api().replace(body=resource_dict, namespace=self.namespace)

    def logs(self, container=None):
        """
        Get resource logs

        Args:
            container (str): Container name to get container logs

        Returns:
            str: Resource logs
        """
        LOGGER.info(f"Get {self.kind} {self.name} logs")
        cmd = f"logs {self.name}"
        if container:
            cmd += f" -c {container}"
        res, out = ext_utils.run_oc_command(command=cmd)
        return res if not res else out

    def search(self, regex):
        """
        Search for resource

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: Resource or None
        """
        raise NotImplementedError


class NamespacedResource(Resource):
    """
    NameSpaced object, inherited from Resource.
    """
    def __init__(self, namespace, name=None):
        super(NamespacedResource, self).__init__(name=name)
        self.namespace = namespace

    def search(self, regex):
        """
        Search for resource

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: Resource or None
        """
        raise NotImplementedError
