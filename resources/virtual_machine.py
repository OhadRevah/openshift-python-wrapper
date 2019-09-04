# -*- coding: utf-8 -*-

import time
import json
import logging

from openshift.dynamic.exceptions import ResourceNotFoundError, ConflictError

from urllib3.exceptions import ProtocolError

from resources.utils import TimeoutExpiredError, TimeoutSampler
from .node import Node
from .pod import Pod
from .resource import TIMEOUT, NamespacedResource

LOGGER = logging.getLogger(__name__)
API_GROUP = "kubevirt.io"


def get_base_vmi_spec():
    return {
        "domain": {
            "devices": {
                "disks": [{"disk": {"bus": "virtio"}, "name": "containerdisk"}]
            },
            "machine": {"type": ""},
            "resources": {"requests": {"memory": "64M"}},
        },
        "terminationGracePeriodSeconds": 0,
        "volumes": [
            {
                "name": "containerdisk",
                "containerDisk": {
                    "image": "kubevirt/cirros-container-disk-demo:latest"
                },
            }
        ],
    }


class AnsibleLoginAnnotationsMixin(object):
    """A mixin class that enhances the object.metadata.annotations
       with login credentials stored in Ansible variables.

       This allows seamless console connection in tests as both
       Console and Ansible inventory/connection plugins know how
       to extract this information.
    """

    def _store_login_information(self, username, password):
        self._username = username
        self._password = password

    def _add_login_annotation(self, vmi):
        """Enhance VMI object with the proper metadata. Call this method
           from to_dict with vmi set to the dict that represents VMI.
           The provided vmi is modified in place!

           This method does nothing when no credentials were provided.
        """

        login_annotation = {}

        if self._username:
            login_annotation["ansible_user"] = self._username

        if self._password:
            login_annotation["ansible_ssh_pass"] = self._password

        if login_annotation:
            # cloud images defaults
            login_annotation["ansible_become"] = True
            login_annotation["ansible_become_method"] = "sudo"

            vmi.setdefault("metadata", {})
            vmi["metadata"].setdefault("annotations", {})
            vmi["metadata"]["annotations"]["ansible"] = json.dumps(login_annotation)


class VirtualMachine(NamespacedResource, AnsibleLoginAnnotationsMixin):
    """
    Virtual Machine object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """

    api_group = API_GROUP

    def __init__(self, name, namespace, client=None, username=None, password=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self._store_login_information(username, password)

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {"template": {"spec": get_base_vmi_spec()}, "running": False}
        self._add_login_annotation(vmi=res["spec"]["template"])

        return res

    def start(self, timeout=TIMEOUT, wait=False):
        """
        Start VM

        Args:
            timeout (int): Time to wait for the resource.
            wait (bool): If True wait else Not

        Raises:
            WaitToBeStartedTimedOut: if VM failed to start.
        """

        self.apply()
        if wait:
            return self.wait_for_status(timeout=timeout, status=True)

    def apply(self):
        retries_on_conflict = 3
        while True:
            try:
                body = self.instance.to_dict()
                body["spec"]["running"] = True
                LOGGER.info(f"Start VM {self.name} Retries left {retries_on_conflict}")
                self.update(body)
                break
            except ConflictError:
                retries_on_conflict -= 1
                if retries_on_conflict == 0:
                    raise
                time.sleep(1)

    def stop(self, timeout=TIMEOUT, wait=False):
        """
        Stop VM

        Args:
            timeout (int): Time to wait for the resource.
            wait (bool): If True wait else Not

        Raises:
            WaitToBeStoppedTimedOut: if VM failed to stop.
        """
        body = self.instance.to_dict()
        body["spec"]["running"] = False
        LOGGER.info(f"Stop VM {self.name}")
        self.update(body)
        if wait:
            return self.wait_for_status(timeout=timeout, status=False)

    def wait_for_status(self, status, timeout=TIMEOUT):
        """
        Wait for resource to be in status

        Args:
            status (bool): Expected status.
            timeout (int): Time to wait for the resource.

        Returns:
            bool: True if resource in desire status, False if timeout reached.
        """
        LOGGER.info(f"Wait for {self.kind} {self.name} status to be {status}")
        samples = TimeoutSampler(
            timeout=timeout,
            sleep=1,
            exceptions=ProtocolError,
            func=self.api().get,
            field_selector=f"metadata.name=={self.name}",
        )
        for sample in samples:
            if sample.items:
                if sample.items[0].spec.running == status:
                    return

    @property
    def vmi(self):
        """
        Get VMI

        Returns:
            VirtualMachineInstance: VMI
        """
        return VirtualMachineInstance(
            name=self.name,
            namespace=self.namespace,
            username=self._username,
            password=self._password,
        )

    def ready(self):
        """
        Get VM status

        Returns:
            bool: True if Running else False
        """
        LOGGER.info(f"Check if {self.kind} {self.name} is ready")
        return self.instance.status["ready"]


class VirtualMachineInstance(NamespacedResource, AnsibleLoginAnnotationsMixin):
    """
    Virtual Machine Instance object, inherited from Resource.
    """

    api_group = API_GROUP

    def __init__(self, name, namespace, client=None, username=None, password=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self._store_login_information(username, password)

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = get_base_vmi_spec()

        self._add_login_annotation(vmi=res)

        return res

    @property
    def interfaces(self):
        return self.instance.status.interfaces

    @property
    def virt_launcher_pod(self):
        pods = list(
            Pod.get(
                dyn_client=self.client,
                namespace=self.namespace,
                label_selector=f"kubevirt.io=virt-launcher,kubevirt.io/created-by={self.instance.metadata.uid}",
            )
        )
        migration_state = self.instance.status.migrationState
        if migration_state:
            #  After VM migration there are two pods, one in Completed status and one in Running status.
            #  We need to return the Pod that is not in Completed status.
            for pod in pods:
                if migration_state.targetPod == pod.name:
                    return pod
        else:
            return pods[0]

        raise ResourceNotFoundError

    def wait_until_running(self, timeout=TIMEOUT, logs=True):
        """
        Wait until VMI is running

        Args:
            timeout (int): Time to wait for VMI.
            logs (bool): True to extract logs from the VMI pod and from the VMI.

        Raises:
            TimeoutExpiredError: If VMI failed to run.
        """
        try:
            self.wait_for_status(status="Running", timeout=timeout)
        except TimeoutExpiredError:
            if not logs:
                raise

            virt_pod = self.virt_launcher_pod
            if virt_pod:
                LOGGER.debug(f"{virt_pod.name} *****LOGS*****")
                LOGGER.debug(virt_pod.log(container="compute"))

            raise

    @property
    def node(self):
        """
        Get the node name where the VM is running

        Returns:
            Node: Node
        """
        return Node(name=self.instance.status.nodeName)

    def get_xml(self):
        """
        Get virtual machine instance XML

        Returns:
            xml_output(string): VMI XML in the multi-line string
        """
        return self.virt_launcher_pod.execute(
            command=["virsh", "dumpxml", f"{self.namespace}_{self.name}"],
            container="compute",
        )


class VirtualMachineInstanceMigration(NamespacedResource):
    api_group = API_GROUP

    def __init__(self, name, namespace, vmi=None, client=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self._vmi = vmi

    def _to_dict(self):
        # When creating VirtualMachineInstanceMigration vmi is mandatory but when calling get()
        # we cannot pass vmi.
        assert self._vmi, "vmi is mandatory for create"

        res = super()._to_dict()
        res["spec"] = {"vmiName": self._vmi.name}
        return res


class VirtualMachineInstancePreset(NamespacedResource):
    """
    VirtualMachineInstancePreset object.
    """

    api_group = API_GROUP


class VirtualMachineInstanceReplicaSet(NamespacedResource):
    """
    VirtualMachineInstancePreset object.
    """

    api_group = API_GROUP
