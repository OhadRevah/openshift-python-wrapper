import logging
import os

import pexpect
from resources.utils import TimeoutSampler

from utilities.constants import OS_LOGIN_PARAMS


LOGGER = logging.getLogger(__name__)


class Console(object):
    USERNAME = PASSWORD = None

    def __init__(self, vm, username=None, password=None, timeout=30):
        """
        Connect to VM console

        Args:
            vm (VirtualMachine): VM resource
            username (str): VM username
            password (str): VM password

        Examples:
            from utilities import console
            with console.Fedora(vm=vm) as vmc:
                vmc.sendline('some command)
                vmc.expect('some output')
        """
        self.vm = vm
        self.username = username or self.USERNAME
        self.password = password or self.PASSWORD
        self.timeout = timeout
        self.child = None
        self.login_prompt = "login:"
        self.prompt = "#" if self.username == "root" else [r"\$"]
        self.cmd = self._generate_cmd()

    def connect(self):
        LOGGER.info(f"Connect to {self.vm.name} console")
        self.console_eof_sampler(pexpect.spawn, self.cmd, [], self.timeout)

        self._connect()

        return self.child

    def _connect(self):
        self.child.send("\n\n")
        self.child.expect(self.login_prompt, timeout=300)
        LOGGER.info(f"{self.vm.name}: Using username {self.username}")
        self.child.sendline(self.username)
        if self.password:
            self.child.expect("Password:")
            LOGGER.info(f"{self.vm.name}: Using password {self.password}")
            self.child.sendline(self.password)
        self.child.expect(self.prompt, timeout=150)
        LOGGER.info(f"{self.vm.name}: Got prompt.")

    def disconnect(self):
        if self.child.terminated:
            self.console_eof_sampler(pexpect.spawn, self.cmd, [], self.timeout)
        self.child.send("\n\n")
        self.child.expect(self.prompt)
        self.child.send("exit")
        self.child.send("\n\n")
        self.child.expect("login:")
        self.child.close()

    def force_disconnect(self):
        """
        Method is a workaround for RHEL 7.7.
        For some reason, console may not be logged out successfully in __exit__()
        """
        self.console_eof_sampler(pexpect.spawn, self.cmd, [], self.timeout)
        self.disconnect()

    def console_eof_sampler(self, func, *func_args):
        sampler = TimeoutSampler(  # noqa: FCFN001
            300,
            5,
            func,
            pexpect.exceptions.EOF,
            *func_args,
        )
        for sample in sampler:
            if sample:
                self.child = sample
                break

    def _generate_cmd(self):
        virtctl = os.environ.get("VIRTCTL", "virtctl")
        cmd = f"{virtctl} console {self.vm.name}"
        if self.vm.namespace:
            cmd += f" -n {self.vm.namespace}"
        return cmd

    def __enter__(self):
        """
        Connect to console
        """
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Logout from shell
        """
        self.disconnect()


class Fedora(Console):
    params = OS_LOGIN_PARAMS["fedora"]
    USERNAME = params["username"]
    PASSWORD = params["password"]


class Cirros(Console):
    params = OS_LOGIN_PARAMS["cirros"]
    USERNAME = params["username"]
    PASSWORD = params["password"]


class Alpine(Console):
    params = OS_LOGIN_PARAMS["alpine"]
    USERNAME = params["username"]
    PASSWORD = params["password"]


class RHEL(Console):
    params = OS_LOGIN_PARAMS["rhel"]
    USERNAME = params["username"]
    PASSWORD = params["password"]


class Centos(Console):
    params = OS_LOGIN_PARAMS["centos"]
    USERNAME = params["username"]
    PASSWORD = params["password"]
