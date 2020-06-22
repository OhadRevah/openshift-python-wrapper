import logging
import os

import ovirtsdk4


class RHV:
    def __init__(self, url, username, password, ca_file=None, debug=False, log=None):
        self.url = url
        self.username = username
        self.password = password
        self.ca_file = ca_file or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "rhv-cert.crt"
        )
        self.debug = debug
        self.log = log or logging.getLogger()
        self.api = None
        if not self.api:
            self.api = self._api

    def __enter__(self):
        self.api = self._api
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.api.close()

    @property
    def _api(self):
        return ovirtsdk4.Connection(
            url=self.url,
            username=self.username,
            password=self.password,
            ca_file=self.ca_file,
            debug=self.debug,
            log=self.log,
        )

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
