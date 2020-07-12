import logging
import os

import ovirtsdk4


class RHV:
    def __init__(
        self,
        url,
        username,
        password,
        ca_file=None,
        debug=False,
        log=None,
        insecure=False,
    ):
        self.url = url
        self.username = username
        self.password = password
        self.ca_file = ca_file
        self.insecure = insecure
        if not self.ca_file:
            self._ca_file()

        self.debug = debug
        self.log = log or logging.getLogger()
        self.api = None
        self.connect()

    def _ca_file(self):
        abs_path = os.path.dirname(os.path.abspath(__file__))
        crt_file = [i for i in os.listdir(abs_path) if i.strip(".crt") in self.url]
        if not crt_file:
            raise ValueError(
                f"CA certificate file for {self.url} not found under {abs_path}"
            )
        self.ca_file = os.path.join(abs_path, crt_file[0])

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.api.close()

    def connect(self):
        self.api = ovirtsdk4.Connection(
            url=self.url,
            username=self.username,
            password=self.password,
            ca_file=self.ca_file,
            debug=self.debug,
            log=self.log,
            insecure=self.insecure,
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
