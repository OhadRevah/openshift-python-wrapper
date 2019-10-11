import json
import logging

import pexpect


LOGGER = logging.getLogger(__name__)


class Console(object):
    _USERNAME = _PASSWORD = None

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
        self.username = username or self._USERNAME
        self.password = password or self._PASSWORD
        self.timeout = timeout
        self.child = None

    def connect(self):
        # No login credentials provided, attempt autodetection
        # and fill in the missing details
        if not all((self.username, self.password)):
            LOGGER.debug(f"Login autodetection for {self.vm.name}")
            raw = self.vm.vmi.instance["metadata"]["annotations"]["ansible"]
            data = json.loads(raw)
            if not self.username and "ansible_user" in data:
                self.username = data["ansible_user"]
            if not self.password and "ansible_ssh_pass" in data:
                self.password = data["ansible_ssh_pass"]
            LOGGER.info(
                f"Login autodetection for {self.vm.name} - {self.username}:{self.password}"
            )

        return self._connect(
            login_prompt="login:",
            username=self.username,
            password=self.password,
            prompt="#" if self.username == "root" else "$",
        )

    def _connect(self, login_prompt, username, password, prompt):
        self.child.send("\n\n")
        self.child.expect(login_prompt, timeout=300)
        LOGGER.info(f"{self.vm.name}: Using username {self.username}")
        self.child.sendline(username)
        if self.password:
            self.child.expect("Password:")
            LOGGER.info(f"{self.vm.name}: Using password {self.password}")
            self.child.sendline(password)
        self.child.expect(prompt)
        LOGGER.info(f"{self.vm.name}: Got prompt.")
        if self.child.after:
            raise ConnectionError(
                f"Failed to open console to {self.vm.name}. error: {self.child.after}"
            )

        return self.child

    def __enter__(self):
        """
        Connect to console
        """
        LOGGER.info(f"Connect to {self.vm.name} console")
        cmd = "virtctl console {vm}".format(vm=self.vm.name)
        if self.vm.namespace:
            cmd += " -n {namespace}".format(namespace=self.vm.namespace)

        self.child = pexpect.spawn(cmd, timeout=self.timeout)
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Logout from shell
        """
        self.child.send("exit")
        self.child.send("\n\n")
        self.child.expect("login:")
        self.child.close()


class Fedora(Console):
    _USERNAME = "fedora"
    _PASSWORD = "fedora"


class Cirros(Console):
    _USERNAME = "cirros"
    _PASSWORD = "gocubsgo"


class Alpine(Console):
    _USERNAME = "root"
    _PASSWORD = None


class RHEL(Console):
    _USERNAME = "cloud-user"
    _PASSWORD = "redhat"
