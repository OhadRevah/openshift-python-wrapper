"""
Test Ansible Module with running test playbooks
"""
import logging
import sh
import pytest
import os

LOGGER = logging.getLogger(__name__)

PLAYBOOK_REPO_URL = "https://github.com/kubevirt/ansible-kubevirt-modules"
PLAYBOOK_REPO_PATH = "ansible-kubevirt-modules/"
PLAYBOOK_REPO_ANSICFG = os.path.join(PLAYBOOK_REPO_PATH, "tests/ansible.cfg")
PLAYBOOK_PATH = os.path.join(PLAYBOOK_REPO_PATH, "tests/playbooks/")
PLAYBOOK_REPO_LOG = os.path.join(PLAYBOOK_REPO_PATH, "ansible.log")


@pytest.fixture(scope="module")
def cloned_playbook_repo(request):
    sh.git.clone(PLAYBOOK_REPO_URL)
    os.environ["ANSIBLE_CONFIG"] = PLAYBOOK_REPO_ANSICFG

    def fin():
        sh.rm(PLAYBOOK_REPO_PATH, "-r")
        del os.environ["ANSIBLE_CONFIG"]

    request.addfinalizer(fin)


@pytest.mark.parametrize(
    "playbook_name",
    [
        "kubevirt_preset.yml",
        "kubevirt_pvc.yml",
        "kubevirt_vmir.yml",
        "kubevirt_template.yaml",
        "kubevirt_vm.yml",
        "e2e.yaml",
    ],
)
def test_ansible_playbook(cloned_playbook_repo, playbook_name):
    """
    Test Each parametrized playbook against ansible devel
    """
    try:
        sh.ansible_playbook(os.path.join(PLAYBOOK_PATH, playbook_name), "-vvvv")
    except sh.ErrorReturnCode as e:
        with open(PLAYBOOK_REPO_LOG, "r") as log:
            LOGGER.debug(log.read())
        pytest.fail(
            f"\nTest for running playbook {playbook_name} failed\n Traceback: {e}"
        )
