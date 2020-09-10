"""
Test Ansible Module with running test playbooks
"""
import logging
import os
import shutil
import subprocess

import pytest
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.template import Template
from resources.virtual_machine import (
    VirtualMachine,
    VirtualMachineInstance,
    VirtualMachineInstancePreset,
    VirtualMachineInstanceReplicaSet,
)
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)

PLAYBOOK_REPO_URL = "https://github.com/kubevirt/ansible-kubevirt-modules"
PLAYBOOK_REPO_PATH = "ansible-kubevirt-modules/"
PLAYBOOK_REPO_ANSICFG = os.path.join(PLAYBOOK_REPO_PATH, "tests/ansible.cfg")
PLAYBOOK_PATH = os.path.join(PLAYBOOK_REPO_PATH, "tests/playbooks/")
PLAYBOOK_REPO_LOG = os.path.join(PLAYBOOK_REPO_PATH, "ansible.log")


@pytest.fixture(scope="module")
def clone_playbook_repo(request):

    # Clone the repo for all the playbooks
    subprocess.check_output(
        f"git clone {PLAYBOOK_REPO_URL}", stderr=subprocess.STDOUT, shell=True
    )
    yield
    # Delete the cloned repo ones used
    shutil.rmtree(PLAYBOOK_REPO_PATH)


@pytest.fixture(scope="module")
def ansible_config_environ():
    os.environ["ANSIBLE_CONFIG"] = PLAYBOOK_REPO_ANSICFG
    yield
    del os.environ["ANSIBLE_CONFIG"]


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_client):
    default_ns = "default"
    vms = list(VirtualMachine.get(admin_client, namespace=default_ns))
    vmirs = list(
        VirtualMachineInstanceReplicaSet.get(admin_client, namespace=default_ns)
    )
    vmis = list(VirtualMachineInstance.get(admin_client, namespace=default_ns))
    vmips = list(VirtualMachineInstancePreset.get(admin_client, namespace=default_ns))
    pvcs = list(PersistentVolumeClaim.get(admin_client, namespace=default_ns))
    try:
        templates = list(
            Template.get(admin_client, singular_name="template", namespace=default_ns)
        )
    except NotImplementedError as e:
        # Templates are only present if tests run with openshift provider
        LOGGER.warning(e)
        templates = []
    yield
    for vm in VirtualMachine.get(admin_client, namespace=default_ns):
        if vm not in vms:
            vm.delete(wait=True)

    for vmir in VirtualMachineInstanceReplicaSet.get(
        admin_client, namespace=default_ns
    ):
        if vmir not in vmirs:
            vmir.delete(wait=True)

    for vmi in VirtualMachineInstance.get(admin_client, namespace=default_ns):
        if vmi not in vmis:
            vmi.delete(wait=True)

    for vmip in VirtualMachineInstancePreset.get(admin_client, namespace=default_ns):
        if vmip not in vmips:
            vmip.delete(wait=True)

    for pvc in PersistentVolumeClaim.get(admin_client, namespace=default_ns):
        if pvc not in pvcs:
            pvc.delete(wait=True)

    try:
        for template in Template.get(
            admin_client, singular_name="template", namespace=default_ns
        ):
            if template not in templates:
                template.delete(wait=True)
    except NotImplementedError:
        # Templates are only present if tests run with openshift provider
        pass


@pytest.mark.parametrize(
    "playbook_name",
    [
        pytest.param("kubevirt_preset.yml", marks=(pytest.mark.polarion("CNV-2575"))),
        pytest.param(
            "kubevirt_vmir.yml",
            marks=(
                pytest.mark.polarion("CNV-2564"),
                pytest.mark.bugzilla(
                    1749704, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param("kubevirt_vm.yml", marks=(pytest.mark.polarion("CNV-2562"))),
        pytest.param(
            "kubevirt_dv_vm.yaml",
            marks=(
                pytest.mark.polarion("CNV-2576"),
                pytest.mark.bugzilla(
                    1730706, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
                pytest.mark.bugzilla(
                    1751744, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
                pytest.mark.jira("CNV-4712", run=False),
            ),
        ),
        pytest.param(
            "kubevirt_template.yaml", marks=(pytest.mark.polarion("CNV-2572"))
        ),
        pytest.param(
            "kubevirt_pvc.yml",
            marks=(
                pytest.mark.polarion("CNV-2563"),
                pytest.mark.bugzilla(
                    1716905, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
                pytest.mark.bugzilla(
                    1751744, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
                pytest.mark.jira("CNV-4712", run=False),
            ),
        ),
        pytest.param(
            "e2e.yaml",
            marks=(
                pytest.mark.polarion("CNV-720"),
                pytest.mark.bugzilla(
                    1749704, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
                pytest.mark.bugzilla(
                    1751744, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
                pytest.mark.jira("CNV-4712", run=False),
            ),
        ),
    ],
)
def test_ansible_playbook(clone_playbook_repo, ansible_config_environ, playbook_name):
    """
    Test Each parametrized playbook against ansible devel
    """

    path = os.path.join(PLAYBOOK_PATH, playbook_name)
    try:
        subprocess.check_output(
            f"ansible-playbook {path} -vvvv", stderr=subprocess.STDOUT, shell=True
        )
    except subprocess.CalledProcessError as e:
        LOGGER.error(e.output)
        with open(PLAYBOOK_REPO_LOG, "r") as log:
            LOGGER.debug(log.read())
        pytest.fail(
            f"\nTest for running playbook {playbook_name} failed\n Traceback: {e}"
        )
