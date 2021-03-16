from pytest_testconfig import config as py_config


# Common templates
RHEL_LATEST = py_config["latest_rhel_os_dict"]
RHEL_LATEST_LABELS = RHEL_LATEST["template_labels"]
RHEL_LATEST_OS = RHEL_LATEST_LABELS["os"]

WINDOWS_LATEST = py_config["latest_windows_os_dict"]
WINDOWS_LATEST_LABELS = WINDOWS_LATEST["template_labels"]
WINDOWS_LATEST_OS = WINDOWS_LATEST_LABELS["os"]

FEDORA_LATEST = py_config["latest_fedora_os_dict"]
FEDORA_LATEST_LABELS = FEDORA_LATEST["template_labels"]
FEDORA_LATEST_OS = FEDORA_LATEST_LABELS["os"]
