import logging
import shlex

from ocp_resources.backup import Backup
from ocp_resources.restore import Restore

from utilities.constants import TIMEOUT_5MIN
from utilities.infra import get_pod_by_name_prefix, unique_name


ADP_NAMESPACE = "openshift-adp"

LOGGER = logging.getLogger(__name__)


def delete_velero_resource(resource, client):
    velero_pod = get_pod_by_name_prefix(
        dyn_client=client, pod_prefix="velero", namespace=ADP_NAMESPACE
    )
    velero_pod.execute(
        command=shlex.split(
            f"bash -c 'echo  Y | ./velero  delete {resource.kind.lower()} {resource.name}'"
        )
    )


class VeleroBackup(Backup):
    def __init__(
        self,
        name,
        namespace=ADP_NAMESPACE,
        included_namespaces=None,
        client=None,
        teardown=False,
        privileged_client=None,
        yaml_file=None,
        excluded_resources=None,
        wait_complete=True,
        timeout=TIMEOUT_5MIN,
        **kwargs,
    ):
        super().__init__(
            name=unique_name(name=name),
            namespace=namespace,
            included_namespaces=included_namespaces,
            client=client,
            teardown=teardown,
            privileged_client=privileged_client,
            yaml_file=yaml_file,
            excluded_resources=excluded_resources,
            **kwargs,
        )
        self.wait_complete = wait_complete
        self.timeout = timeout

    def __enter__(self):
        super().__enter__()
        if self.wait_complete:
            self.wait_for_status(
                status=self.Status.COMPLETED,
                timeout=self.timeout,
            )
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        delete_velero_resource(resource=self, client=self.client)


class VeleroRestore(Restore):
    def __init__(
        self,
        name,
        namespace=ADP_NAMESPACE,
        included_namespaces=None,
        backup_name=None,
        client=None,
        teardown=False,
        privileged_client=None,
        yaml_file=None,
        wait_complete=True,
        timeout=TIMEOUT_5MIN,
        **kwargs,
    ):
        super().__init__(
            name=unique_name(name=name),
            namespace=namespace,
            included_namespaces=included_namespaces,
            backup_name=backup_name,
            client=client,
            teardown=teardown,
            privileged_client=privileged_client,
            yaml_file=yaml_file,
            **kwargs,
        )
        self.wait_complete = wait_complete
        self.timeout = timeout

    def __enter__(self):
        super().__enter__()
        if self.wait_complete:
            self.wait_for_status(
                status=self.Status.COMPLETED,
                timeout=self.timeout,
            )
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        delete_velero_resource(resource=self, client=self.client)
