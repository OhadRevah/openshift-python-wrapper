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
