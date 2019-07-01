import logging

import pexpect

LOGGER = logging.getLogger(__name__)


class Console(object):
    _USERNAME = _PASSWORD = None

    def __init__(self, vm, namespace, username=None, password=None):
        """
        Connect to VM console

        Examples:
            from utilities import console
            with console.Fedora(vm=vm_name) as vmc:
                vmc.sendline('some command)
                vmc.expect('some output')
        """
        self.vm = vm
        self.username = username or self._USERNAME
        self.password = password or self._PASSWORD
        self.namespace = namespace
        self.child = None

    def connect(self):
        return self._connect(
            login_prompt="login:",
            username=self.username,
            password=self.password,
            prompt="#" if self.username == "root" else "$",
        )

    def _connect(self, login_prompt, username, password, prompt):
        self.child.send("\n\n")
        self.child.expect(login_prompt)
        self.child.sendline(username)
        if self.password:
            self.child.expect("Password:")
            self.child.sendline(password)
        self.child.expect(prompt)
        if self.child.after:
            LOGGER.error(self.err_msg.format(vm=self.vm, error=self.child.after))
            return False

        return self.child

    def __enter__(self):
        """
        Connect to console
        """
        LOGGER.info(f"Connect to {self.vm} console")
        self.err_msg = "Failed to get console to {vm}. error: {error}"
        cmd = "virtctl console {vm}".format(vm=self.vm)
        if self.namespace:
            cmd += " -n {namespace}".format(namespace=self.namespace)

        self.child = pexpect.spawn(cmd, encoding="utf-8")
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
