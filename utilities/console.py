
import logging
from autologs.autologs import generate_logs


import pexpect

LOGGER = logging.getLogger(__name__)


class DistroNotSupported(Exception):
    pass


class Console(object):
    def __init__(self):
        """
        Connect to VM console

        Examples:
            from utilities import console
            with console.Fedora(vm=vm_name) as vmc:
                vmc.sendline('some command)
                vmc.expect('some output')
        """
        self.vm = None
        self.username = None
        self.password = None
        self.namespace = None

    def _connect(self):
        """
        Connect to console
        """
        self.err_msg = "Failed to get console to {vm}. error: {error}"
        cmd = "virtctl console {vm}".format(vm=self.vm)
        if self.namespace:
            cmd += " -n {namespace}".format(namespace=self.namespace)

        self.child = pexpect.spawn(cmd, encoding='utf-8')

    def _exit(self):
        """
        Logout from shell
        """
        self.child.send("exit")
        self.child.send("\n\n")
        self.child.expect("login:")
        self.child.close()


class Fedora(Console):
    def __init__(self, vm, username=None, password=None, namespace=None):
        """
        Connect to Fedora VM console

        Args:
            vm (str): VM name.
            username (str): Username for login.
            password (str): Password for login.
            namespace (str): VM namespace
        """
        super(Fedora, self).__init__()
        self.vm = vm
        self.username = username or "fedora"
        self.password = password or "fedora"
        self.namespace = namespace
        self._connect()

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._exit()

    @generate_logs()
    def connect(self):
        """
        Connect to Fedora

        Returns:
            spawn: Spawn object
        """
        self.child.send("\n\n")
        self.child.expect("login:")
        self.child.sendline(self.username)
        self.child.expect("Password:")
        self.child.sendline(self.password)
        self.child.expect("$")
        if self.child.after:
            LOGGER.error(self.err_msg.format(vm=self.vm, error=self.child.after))
            return False

        return self.child


class Cirros(Console):
    def __init__(self, vm, username=None, password=None, namespace=None):
        """
        Connect to Cirros VM console

        Args:
            vm (str): VM name.
            username (str): Username for login.
            password (str): Password for login.
            namespace (str): VM namespace
        """
        super(Cirros, self).__init__()
        self.vm = vm
        self.username = username or "cirros"
        self.password = password or "gocubsgo"
        self.namespace = namespace
        self._connect()

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._exit()

    @generate_logs()
    def connect(self):
        """
        Connect to Cirros

        Returns:
            spawn: Spawn object
        """
        self.child.send("\n\n")
        self.child.expect("login as 'cirros' user. default password: 'gocubsgo'. use 'sudo' for root.")
        self.child.send("\n")
        self.child.expect("login:")
        self.child.sendline(self.username)
        self.child.expect("Password:")
        self.child.sendline(self.password)
        self.child.expect("\\$")
        if self.child.after:
            LOGGER.error(self.err_msg.format(vm=self.vm, error=self.child.after))
            return False

        return self.child


class Alpine(Console):
    def __init__(self, vm, username=None, password=None, namespace=None):
        """
        Connect to Alpine VM console

        Args:
            vm (str): VM name.
            username (str): Username for login.
            password (str): Password for login.
            namespace (str): VM namespace
        """
        super(Alpine, self).__init__()
        self.vm = vm
        self.username = username or "root"
        self.password = password
        self.namespace = namespace
        self._connect()

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._exit()

    @generate_logs()
    def connect(self):
        """
        Connect to Alpine

        Returns:
            spawn: Spawn object
        """
        self.child.send("\n\n")
        self.child.expect("localhost login:")
        self.child.sendline(self.username or "root")
        if self.password:
            self.child.expect("Password:")
            self.child.sendline(self.password)
        self.child.expect("localhost:~#")
        if self.child.after:
            LOGGER.error(self.err_msg.format(vm=self.vm, error=self.child.after))
            return False

        return self.child
