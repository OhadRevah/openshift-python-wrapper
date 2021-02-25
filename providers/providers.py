import abc
import logging
import re

import ovirtsdk4
from pyVim.connect import Disconnect, SmartConnectNoSSL
from pyVmomi import vim
from resources.utils import TimeoutSampler

from utilities.infra import MissingResourceException


class Provider(abc.ABC):
    def __init__(
        self,
        username,
        password,
        host,
        debug=False,
        log=None,
    ):
        self.username = username
        self.password = password
        self.host = host
        self.debug = debug
        self.log = log or logging.getLogger()
        self.api = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    @abc.abstractmethod
    def connect(self):
        pass

    @abc.abstractmethod
    def disconnect(self):
        pass

    @abc.abstractmethod
    def test(self):
        pass


class RHV(Provider):
    """
    https://github.com/oVirt/ovirt-engine-sdk/tree/master/sdk/examples
    """

    def __init__(
        self,
        host,
        username,
        password,
        ca_file,
        debug=False,
        log=None,
        insecure=False,
    ):
        super().__init__(
            host=host,
            username=username,
            password=password,
            debug=debug,
            log=log,
        )
        self.insecure = insecure
        self.ca_file = ca_file

    def disconnect(self):
        self.api.close()

    def connect(self):
        self.api = ovirtsdk4.Connection(
            url=self.host,
            username=self.username,
            password=self.password,
            ca_file=self.ca_file,
            debug=self.debug,
            log=self.log,
            insecure=self.insecure,
        )
        return self

    @property
    def test(self):
        return self.api.test()

    @property
    def vms_services(self):
        return self.api.system_service().vms_service()

    def vms(self, search):
        return self.vms_services.list(search=search)

    def vm(self, name, cluster=None):
        query = f"name={name}"
        if cluster:
            query = f"{query} cluster={cluster}"

        return self.vms(search=query)[0]

    def vm_nics(self, vm):
        return self.vms_services.vm_service(vm.id).nics_service().list()

    def vm_disk_attachments(self, vm):
        return self.vms_services.vm_service(vm.id).disk_attachments_service().list()

    def start_vm(self, vm):
        self.vms_services.vm_service(vm.id).start()


class VMWare(Provider):
    """
    https://github.com/vmware/vsphere-automation-sdk-python
    """

    def __init__(
        self,
        host,
        username,
        password,
        thumbprint,
        debug=False,
        log=None,
    ):
        super().__init__(
            host=host,
            username=username,
            password=password,
            debug=debug,
            log=log,
        )
        self.thumbprint = thumbprint

    def disconnect(self):
        Disconnect(si=self.api)

    def connect(self):

        self.api = SmartConnectNoSSL(  # ssl cert check is not required
            host=self.host,
            user=self.username,
            pwd=self.password,
            thumbprint=self.thumbprint,
        )

    @property
    def test(self):
        return True

    @property
    def content(self):
        return self.api.RetrieveContent()

    def vms(self, search=None):
        container = self.content.rootFolder  # starting point to look into
        view_type = [vim.VirtualMachine]  # object types to look for
        recursive = True  # whether we should look into it recursively
        container_view = self.content.viewManager.CreateContainerView(
            container, view_type, recursive
        )

        vms = container_view.view
        if not search:
            return vms

        pat = re.compile(search, re.IGNORECASE)
        for vm in vms:
            if pat.search(vm.summary.config.name) is not None:
                return vm

    def vm(self, name, datacenter=None, cluster=None):
        if cluster:
            _cluster = self.cluster(name=cluster, datacenter=datacenter)
            for host in _cluster.host:
                for vm in host.vm:
                    if vm.summary.config.name == name:
                        return vm

        return self.vms(search=name)

    @property
    def datacenters(self):
        return self.content.rootFolder.childEntity

    def clusters(self, datacenter=None):
        all_clusters = []
        for dc in self.datacenters:  # Iterate though DataCenters
            clusters = dc.hostFolder.childEntity
            if dc.name == datacenter:
                return clusters

            if datacenter:
                continue

            for cluster in clusters:  # Iterate through the clusters in the DC
                all_clusters.append(cluster)

        return all_clusters

    def cluster(self, name, datacenter=None):
        for cluster in self.clusters(datacenter=datacenter):
            if cluster.name == name:
                return cluster

    def get_resource_obj(self, resource_type, resource_name):
        """
        Get the vsphere resource object associated with a given resource_name.
        """
        containers = self.content.viewManager.CreateContainerView(
            container=self.content.rootFolder, type=resource_type, recursive=True
        )
        for cont_obj in containers.view:
            if cont_obj.name == resource_name:
                return cont_obj

        raise MissingResourceException(f"{resource_type}: {resource_name}")

    def wait_task(self, task, action_name="job"):
        """
        Waits and provides updates on a vSphere task.
        """
        for sample in TimeoutSampler(
            wait_timeout=60,
            sleep=2,
            func=lambda: task.info.state != vim.TaskInfo.State.running,
        ):
            if sample:
                break

        if task.info.state == vim.TaskInfo.State.success:
            self.log.info(
                msg=(
                    f"{action_name} completed successfully. "
                    f"{f'result: {task.info.result}' if task.info.result else ''}"
                )
            )
            return task.info.result

        self.log.error(
            msg=f"{action_name} did not complete successfully: {task.info.error}"
        )
        raise task.info.error  # should be a Fault

    def get_vm_clone_spec(self, cluster_name, power_on, vm_flavor, datastore_name):
        cluster = self.cluster(name=cluster_name)
        resource_pool = cluster.resourcePool
        # Relocation spec
        relospec = vim.vm.RelocateSpec()
        relospec.pool = resource_pool

        if datastore_name:
            data_store = self.get_resource_obj(
                resource_type=[vim.Datastore],
                resource_name=datastore_name,
            )
            relospec.datastore = data_store

        vmconf = vim.vm.ConfigSpec()
        if vm_flavor:
            # VM config spec
            vmconf.numCPUs = vm_flavor["cpus"]
            vmconf.memoryMB = vm_flavor["memory"]

        clone_spec = vim.vm.CloneSpec(
            powerOn=power_on,
            template=False,
            location=relospec,
            customization=None,
            config=vmconf,
        )

        return clone_spec

    def clone_vm_from_template(
        self,
        cluster_name,
        template_name,
        vm_name,
        power_on=True,
        vm_flavor=None,
        datastore_name=None,
    ):
        """
        This method will create a new vm by cloning the template provided using template_name.
        By default it uses the spec of the template to create new vm.
        vm_flavor and datastore_name can be changed if required.
        vm_flavor (dict): {'cpu': <number of vCPU>, 'memory':<RAM size in MB>}
        datastore_name (str): '<new datastore name>'
        """
        template_vm = self.get_resource_obj(
            resource_type=[vim.VirtualMachine],
            resource_name=template_name,
        )
        clone_spec = self.get_vm_clone_spec(
            cluster_name=cluster_name,
            power_on=power_on,
            vm_flavor=vm_flavor,
            datastore_name=datastore_name,
        )
        # Creating clone task
        task = template_vm.Clone(
            name=vm_name, folder=template_vm.parent, spec=clone_spec
        )
        return self.wait_task(task=task, action_name="VM clone task")
