import logging
import os

import urllib3
import yaml
from autologs.autologs import generate_logs
from kubernetes import config as kube_config
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError

from utilities import utils

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120
SLEEP = 1


class Resource(object):
    """
    DynamicClient Resource class
    """
    def __init__(self, name=None, api_version=None, kind=None, namespace=None):
        """
        Create DynamicClient

        Args:
            name (str): Resource name
            api_version (str): Resource API version
            kind (str): Resource kind
            namespace (str): Resource namespace
        """
        urllib3.disable_warnings()
        try:
            kubeconfig = os.getenv('KUBECONFIG')
            self.client = DynamicClient(kube_config.new_client_from_config(config_file=kubeconfig))
        except (kube_config.ConfigException, urllib3.exceptions.MaxRetryError):
            LOGGER.error('You need to be login to cluster or have $KUBECONFIG env configured')
            raise

        self.kind = kind
        self.namespace = namespace
        self.api_version = api_version
        self.name = name

    @generate_logs(info=False)
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
            namespace

        Returns:
            Resource: Resource object.
        """
        return self.client.resources.get(api_version=self.api_version, kind=self.kind, **kwargs)

    @generate_logs(info=False)
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
            dict: Resource dict.
        """
        LOGGER.info(f"Get resource {self.name}")
        kwargs['namespace'] = self.namespace
        resources = self.list(**kwargs)
        res = [i for i in resources if i.get('metadata', {}).get('name') == self.name]
        return res[0] if res else {}

    @generate_logs(info=False)
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
            namespace

        Returns:
            list: Resources.
        """
        LOGGER.info(f"Get all resources names of kind {self.kind}")
        return self.api().get(**kwargs).items

    @generate_logs(info=False)
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
        LOGGER.info(f"Get all resources names of kind {self.kind}")
        list_items = self.api().get(**kwargs).items
        return [i.get('metadata', {}).get('name') for i in list_items]

    @generate_logs(info=False)
    def wait(self, timeout=TIMEOUT, **kwargs):
        """
        Wait for resource

        Args:
            timeout (int): Time to wait for the resource.

        Keyword Args:
            name
            label_selector
            field_selector
            resource_version

        Returns:
            bool: True if resource exists, False if timeout reached.
        """
        LOGGER.info(f"Wait until {self.name} is created")
        resources = self.api(**kwargs)
        for rsc in resources.watch(namespace=self.namespace, timeout=timeout, **kwargs):
            if rsc.get('raw_object', {}).get('metadata', {}).get('name') == self.name:
                if rsc.get('type') == 'ADDED':
                    return True
        return False

    @generate_logs(info=False)
    def wait_until_gone(self, timeout=TIMEOUT, sleep=SLEEP):
        """
        Wait until resource is gone

        Args:
            timeout (int): Time to wait for the resource.
            sleep (int): Time to sleep between retries.

        Returns:
            bool: True if resource is gone, False if timeout reached.
        """
        LOGGER.info(f"Wait until {self.name} is gone")
        sample = utils.TimeoutSampler(timeout=timeout, sleep=sleep, func=lambda: bool(self.get()))
        return sample.wait_for_func_status(result=False)

    @generate_logs(info=False)
    def wait_for_status(self, status, timeout=TIMEOUT, **kwargs):
        """
        Wait for resource to be in status

        Args:
            status (str): Expected status.
            timeout (int): Time to wait for the resource.

        Returns:
            bool: True if resource in desire status, False if timeout reached.
        """
        LOGGER.info(f"Wait for {self.name} status to be {status}")
        resources = self.api(**kwargs)
        for rsc in resources.watch(namespace=self.namespace, timeout=timeout, **kwargs):
            if rsc.get('raw_object', {}).get('status', {}).get('phase') == status:
                return True
        return False

    @generate_logs(info=False)
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
            res = utils.run_oc_command(command=f'create -f {yaml_file}', namespace=self.namespace)[0]

        else:
            if not resource_dict:
                resource_dict = {
                    'apiVersion': self.api_version,
                    'kind': self.kind,
                    'metadata': {'name': self.namespace}
                }

            resource_list = self.api()
            res = resource_list.create(body=resource_dict, namespace=self.namespace)

        LOGGER.info(f"Create {self.name}")
        if wait and res:
            return self.wait()
        return res

    @generate_logs(info=False)
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
            res = utils.run_oc_command(command=f'delete -f {yaml_file}', namespace=self.namespace)[0]

        else:
            resource_list = self.api()
            try:
                res = resource_list.delete(name=self.name, namespace=self.namespace)
            except NotFoundError:
                return False

        LOGGER.info(f"Delete {self.name}")
        if wait and res:
            return self.wait_until_gone()
        return res

    @generate_logs(info=False)
    def status(self):
        """
        Get resource status

        Status: Running, Scheduling, Pending, Unknown, CrashLoopBackOff

        Returns:
           str: Status
        """
        LOGGER.info(f"Get {self.name} status")
        return self.get().status.phase

    def _extract_data_from_yaml(self, yaml_data):
        """
        Extract data from yaml stream

        Args:
            yaml_data (dict): Dict from yaml file
        """
        namespace = yaml_data.get('metadata').get('namespace')
        self.namespace = self.namespace or namespace
        self.name = yaml_data.get('metadata').get('name')
        self.api_version = yaml_data.get('apiVersion')
        self.kind = yaml_data.get('kind')

    @generate_logs(info=False)
    def update(self, resource_dict):
        """
        Update resource with resource dict

        Args:
            resource_dict: Resource dictionary
        """
        LOGGER.info(f"Update {self.name}")
        resource_list = self.api()
        resource_list.replace(body=resource_dict, namespace=self.namespace)

    @generate_logs(info=False)
    def logs(self, container=None):
        """
        Get resource logs

        Args:
            container (str): Container name to get container logs

        Returns:
            str: Resource logs
        """
        LOGGER.info(f"Get {self.name} logs")
        cmd = f"logs {self.name}"
        if container:
            cmd += f" -c {container}"
        res, out = utils.run_oc_command(command=cmd)
        return res if not res else out

    def search(self, regex):
        """
        Search for resource using regex

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            str: Resource name
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        return res[0] if res else ""
