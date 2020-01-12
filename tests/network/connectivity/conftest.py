import pytest


@pytest.fixture(scope="session")
def skip_rhel7_workers_masquerade(rhel7_workers):
    if rhel7_workers:
        # https://bugzilla.redhat.com/show_bug.cgi?id=1787576
        pytest.skip(msg="Masquerade not working on RHEL7 workers.")
