import logging
import os
import re
import subprocess

import jinja2
import yaml
from autologs.autologs import generate_logs


LOGGER = logging.getLogger(__name__)


class MissingTemplateVariables(Exception):
    def __init__(self, var, template):
        self.var = var
        self.template = template

    def __str__(self):
        return f"Missing variables {self.var} for template {self.template}"


@generate_logs()
def _run_command(command):
    """
    Run command locally.

    Args:
        command (list): Command to run.

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if err:
        LOGGER.error("Failed to run {cmd}. error: {err}".format(cmd=command, err=err))
        return False, err

    if p.returncode != 0:
        LOGGER.error(
            "Failed to run {cmd}. rc: {rc}".format(cmd=command, rc=p.returncode)
        )
        return False, out.decode("utf-8")

    return True, out.decode("utf-8")


def run_virtctl_command(command, namespace=None):
    """
    Run virtctl command

    Args:
        command (list): Command to run
        namespace (str): Namespace to send to virtctl command

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    virtctl_cmd = ["virtctl"]
    kubeconfig = os.getenv("KUBECONFIG")
    if namespace:
        virtctl_cmd = virtctl_cmd + ["-n", namespace]

    if kubeconfig:
        virtctl_cmd = virtctl_cmd + ["--kubeconfig", kubeconfig]

    virtctl_cmd = virtctl_cmd + command
    return _run_command(command=virtctl_cmd)


@generate_logs()
def generate_yaml_from_template(file_, **kwargs):
    """
    Generate JSON from yaml file_

    Args:
        file_ (str): Yaml file

    Keyword Args:
        name (str):
        image (str):

    Returns:
        dict: Generated from template file

    Raises:
        MissingTemplateVariables: If not all template variables exists

    Examples:
        generate_yaml_from_template(file_='path/to/file/name', name='vm-name-1')
    """
    with open(file_, "r") as stream:
        data = stream.read()

    # Find all template variables
    template_vars = [i.split()[1] for i in re.findall(r"{{ .* }}", data)]
    for var in template_vars:
        if var not in kwargs.keys():
            raise MissingTemplateVariables(var=var, template=file_)
    template = jinja2.Template(data)
    out = template.render(**kwargs)
    return yaml.safe_load(out)
