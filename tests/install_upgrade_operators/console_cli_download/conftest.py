import logging
import re

import pytest
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.route import Route

from tests.install_upgrade_operators.console_cli_download.utils import (
    download_and_extract_virtctl_from_cluster,
)
from utilities.constants import HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD
from utilities.infra import run_command


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def console_cli_downloads_spec_links(admin_client):
    """
    Get console cli downloads spec links

    Returns:
        ConsoleCLIDownload instance.spec.links
    """
    console_cli_download_resource_content = ConsoleCLIDownload(
        name="virtctl-clidownloads-kubevirt-hyperconverged", client=admin_client
    )
    assert console_cli_download_resource_content.exists
    return console_cli_download_resource_content.instance.spec.links


@pytest.fixture()
def all_virtctl_urls(console_cli_downloads_spec_links):
    """This fixture returns URLs for the various OSs to download virtctl"""
    all_virtctl_urls = [entry["href"] for entry in console_cli_downloads_spec_links]
    assert all_virtctl_urls, (
        "No URL entries found in the resource: "
        f"console_cli_download_resource_content={console_cli_downloads_spec_links}"
    )
    return all_virtctl_urls


@pytest.fixture()
def internal_fqdn(admin_client, hco_namespace):
    """
    This fixture returns the prefix url for the cluster, which is used to identify if certain links are routed or
    served from within the cluster
    """
    cluster_route = Route(
        name=HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD, namespace=hco_namespace.name
    )
    assert cluster_route.exists
    return cluster_route.instance.spec.host


@pytest.fixture()
def non_internal_fqdns(all_virtctl_urls, internal_fqdn):
    """
    Get URLs containing FQDN that is not matching the cluster's route

    Returns:
        list: list of all non-internal FQDNs
    """
    return [
        virtctl_url
        for virtctl_url in all_virtctl_urls
        if f"//{internal_fqdn}" not in virtctl_url
    ]


@pytest.fixture()
def downloaded_and_extracted_virtctl_binary_for_os(request, all_virtctl_urls, tmpdir):
    """
    This fixture downloads the virtctl archive from the provided OS, and extracts it to a temporary dir
    """
    url_for_os = [url for url in all_virtctl_urls if request.param in url][0]
    extracted_files = download_and_extract_virtctl_from_cluster(
        tmpdir=tmpdir, virtctl_url=url_for_os
    )
    assert (
        len(extracted_files) == 1
    ), f"Only a single file expected in archive: extracted_files={extracted_files}"
    return extracted_files[0]


@pytest.fixture()
def virtctl_client_and_server_versions(downloaded_and_extracted_virtctl_binary_for_os):
    """
    Get the client and server versions from the virtctl version command

    Returns:
        list: re results (client and server virtctl versions)
    """
    _, virtctl_output, _ = run_command(
        command=[f"{downloaded_and_extracted_virtctl_binary_for_os} version"],
        shell=True,
    )
    client_and_server_versions = re.findall(
        r'(?:Client|Server).*version.*{GitVersion:"v(.*)",\s+GitCommit',
        virtctl_output,
    )
    return client_and_server_versions
