import pytest
from resources.console_cli_download import ConsoleCLIDownload


@pytest.fixture()
def virtctl_ccd(admin_client):
    for ccd in ConsoleCLIDownload.get(
        dyn_client=admin_client, name="virtctl-clidownloads-kubevirt-hyperconverged"
    ):
        return ccd
