import io
import logging
import os
import tarfile
import zipfile

import requests


LOGGER = logging.getLogger(__name__)


def download_and_extract_virtctl_from_cluster(tmpdir, virtctl_url):
    """
    Download and extract the virtctl archive that includes the virtctl binary from the cluster

    Args:
        tmpdir (py.path.local): temporary folder to download the files
        virtctl_url (str): virtctl URL

    Returns:
        list: list of extracted filenames
    """
    LOGGER.info(f"Downloading virtctl archive: url={virtctl_url}")
    requests.packages.urllib3.disable_warnings()
    response = requests.get(virtctl_url, verify=False)
    assert response.status_code == 200
    archive_file_data = io.BytesIO(initial_bytes=response.content)
    LOGGER.info("Extract the archive")
    if virtctl_url.endswith(".zip"):
        archive_file_object = zipfile.ZipFile(file=archive_file_data)
    else:
        archive_file_object = tarfile.open(fileobj=archive_file_data, mode="r")
    archive_file_object.extractall(path=tmpdir)
    extracted_filenames = (
        archive_file_object.namelist()
        if virtctl_url.endswith(".zip")
        else archive_file_object.getnames()
    )
    return [os.path.join(tmpdir.strpath, namelist) for namelist in extracted_filenames]
