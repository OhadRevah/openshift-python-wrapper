"""
Test Ansible Module with running test playbooks
"""
import logging
import pytest
import os
import shutil
import subprocess

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


@pytest.mark.parametrize(
    "playbook_name",
    [
        pytest.param("kubevirt_preset.yml", marks=(pytest.mark.polarion("CNV-2575"))),
        pytest.param("kubevirt_vmir.yml", marks=(pytest.mark.polarion("CNV-2564"))),
        pytest.param("kubevirt_vm.yml", marks=(pytest.mark.polarion("CNV-2562"))),
        pytest.param("kubevirt_dv_vm.yaml", marks=(pytest.mark.polarion("CNV-2576"))),
        pytest.param(
            "kubevirt_template.yaml", marks=(pytest.mark.polarion("CNV-2572"))
        ),
        pytest.param(
            "kubevirt_pvc.yml",
            marks=(pytest.mark.polarion("CNV-2563"), pytest.mark.bugzilla(1716905)),
        ),
        pytest.param(
            "e2e.yaml",
            marks=(pytest.mark.polarion("CNV-720"), pytest.mark.bugzilla(1716905)),
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
