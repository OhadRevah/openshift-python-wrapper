from __future__ import absolute_import, division, print_function

import base64
import os
import re
import uuid

import pexpect
from ansible.errors import AnsibleFileNotFound
from ansible.module_utils._text import to_native
from ansible.plugins.connection import ConnectionBase


__metaclass__ = type


try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display

    display = Display()


DOCUMENTATION = """
    author: Martin Sivak <msivak@redhat.com>
    connection: virtctl
    short_description: Run tasks in kubevirt VMs using virtctl console
    description:
        - Run commands or put/fetch files to an existing kubevirt virtual machine instance using virtctl console
    version_added: '2.8'
    options:
      remote_addr:
        description: Virtual machine name
        default: inventory_hostname
        vars:
            - name: ansible_host
            - name: virtctl_name
      virtctl_namespace:
        description: Virtual machine namespace
        vars:
            - name: virtctl_namespace
      login_prompt:
        description: Default login prompt
        default: 'login:'
        vars:
            - name: login_prompt
      password_prompt:
        description: Default password prompt
        default: 'Password:'
        vars:
            - name: password_prompt
      virtctl_executable:
          default: virtctl
          description:
            - This defines the location of the virtctl binary. It defaults
              to ``virtctl`` which will use the first virtctl binary
              available in $PATH.
            - This option is usually not required, it might be useful
              when using ssh wrappers to connect to remote hosts like
              in minishift environment.
          env: [{name: ANSIBLE_VIRTCTL_EXECUTABLE}]
          vars:
              - name: ansible_virtctl_executable
              - name: virtctl_executable
"""


class Connection(ConnectionBase):
    """Connection plugin that uses virtctl console to open a pty "connection"
       to a VM. It then logs in using the standard ansible credentials.

       File transfers are done using base64 encoded data over standard
       input and output. `base64` binary is required in the guest."""

    transport = "virtctl"
    has_pipelining = True

    PROMPT_DISPLAYED_RE = re.compile("[$#] ?$")

    def __init__(self, *args, **kwargs):
        super(Connection, self).__init__(*args, **kwargs)

        self.user = self._play_context.remote_user

    def set_options(self, *args, **kwargs):
        super(Connection, self).set_options(*args, **kwargs)

        self.namespace = self.get_option("virtctl_namespace")
        self.login_prompt = self.get_option("login_prompt")
        self.password_prompt = self.get_option("password_prompt")
        self.virtctl = self.get_option("virtctl_executable")
        self.host = self.get_option("remote_addr")

    def _mark(self):
        "Generate unique mark symbol"
        return "=" * 20 + str(uuid.uuid1()) + "=" * 20

    def exec_command(self, cmd, in_data=None, sudoable=True):
        """Run a command on the remote host"""
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        display.vvv(u"RUNNING COMMAND...")
        mark = self._mark()

        # Send command
        self._process.write("\n")
        self._process.write(cmd)
        self._process.write(" ; echo $? && echo ")
        self._process.write(mark)
        self._process.write("\n")

        # Retrieve output
        lines = b""
        while True:
            line = self._process.readline()
            display.vvv(">> " + line.decode())
            if line.strip() == mark.encode():
                break
            lines += line

        # Parse out return code and output
        regex_pattern = r"((?P<output>(?:.|\n)*)(?:\r|\n)+)?(?P<retcode>\d+)(?:\r|\n)+"
        matches = re.match(regex_pattern, lines.decode(), re.MULTILINE)
        stdout = matches.group("output") or ""
        returncode = matches.group("retcode")
        returncode = int(returncode)

        # There is no good way to distinguish stdout from stderr when
        # connected via console.
        stderr = ""

        self._eat_prompt(self._process)
        return returncode, stdout, stderr

    def put_file(self, in_path, out_path):
        """Transfer a file from local to remote using stdin/stdout and base64."""
        super(Connection, self).put_file(in_path, out_path)
        display.vvv(u"PUT {0} TO {1}".format(in_path, out_path), host=self.host)
        if not os.path.exists(in_path):
            raise AnsibleFileNotFound(
                "file does not exist: {0}".format(to_native(in_path))
            )

        mark = self._mark()

        self._process.write("base64 -d > " + out_path)
        self._process.write(' && printf "' + mark + '\n"')
        self._process.write("\n")
        with open(in_path, "rb") as fd:
            while True:
                raw_content = fd.read(512)
                if len(raw_content) == 0:
                    break
                encoded_content = base64.b64encode(raw_content)
                self._process.write(encoded_content.decode())
                self._process.write("\n")
        self._process.write("\n")
        self._process.sendcontrol("d")
        while True:
            line = self._process.readline()
            if line.strip() == mark.encode():
                break
        self._eat_prompt(self._process)

    def fetch_file(self, in_path, out_path):
        """Fetch a file from remote using stdin/stdout and base64."""
        super(Connection, self).fetch_file(in_path, out_path)
        display.vvv(u"GET {0} TO {1}".format(in_path, out_path), host=self.host)
        mark = self._mark()

        self._process.write("base64 " + in_path)
        self._process.write(' && printf "' + mark + '\n"')
        self._process.write("\n")
        with open(out_path, "wb") as fd:
            while True:
                raw_content = self._process.readline()
                if raw_content.strip() == mark.encode():
                    break
                decoded_content = base64.b64decode(raw_content)
                fd.write(decoded_content.decode())
        self._eat_prompt(self._process)

    def _connect(self):
        display.vvv(
            u"ESTABLISH VIRT CONSOLE CONNECTION FOR USER: {0}".format(
                self.user, host=self.host
            )
        )
        cmd = "{exe} console {host}".format(exe=self.virtctl, host=self.host)
        if self.namespace:
            cmd += " -n {namespace}".format(namespace=self.namespace)
        process = pexpect.spawn(cmd)
        process.send("\n\n")
        process.readline()

        # TODO Detect stale prompt and logout first ?

        process.expect(self.login_prompt)
        process.sendline(self.user)
        process.expect(self.password_prompt)
        process.sendline(self._play_context.password)
        self._eat_prompt(process)

        # Synchronization lost or login failed?
        if process.after:
            display.vvv("Unexpected input> {}".format(process.after))

        self._connected = True
        self._process = process
        display.vvv(u"VIRT CONSOLE CONNECTION FOR USER {0} IS READY".format(self.user))

    def _eat_prompt(self, process):
        # after logged in
        # there is some prompt like `[root@vultr ~]# `
        process.expect(r"(\[[^]]+\])?[#$] ".encode())

    def close(self):
        super(Connection, self).close()
        display.vvv(
            u"VIRT CONSOLE CONNECTION FOR USER {0} IS TERMINATING".format(self.user)
        )
        self._process.send("\n\n")
        self._process.sendcontrol("d")
        self._process.expect(self.login_prompt)
        self._process.close()
        self._connected = False
        display.vvv(u"VIRT CONSOLE CONNECTION FOR USER {0} IS CLOSED".format(self.user))
