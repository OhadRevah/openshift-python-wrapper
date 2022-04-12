import os
import re
from configparser import ConfigParser
from pathlib import Path
from xmlrpc.client import Fault

import bugzilla
from git import Repo
from packaging.version import InvalidVersion, Version


BUG_STATUS_CLOSED = ("VERIFIED", "CLOSED", "RELEASE_PENDING")
KNOWN_BRANCHES = {"master": "4.11", "cnv-4.10": "4.10"}


class ParentBranchNotFound(Exception):
    pass


def print_status(status_dict):
    for key, value in status_dict.items():
        print(f"    {key}:  {' '.join(list(set(value)))}")


def get_parent_branch():
    repo = Repo(path=".")
    for parent in repo.head.commit.iter_parents():
        commit_parent = parent.name_rev
        if "/" in commit_parent:
            # In some cases we get remotes/origin/<branch>
            return KNOWN_BRANCHES[commit_parent.rsplit("/", 1)[-1]]
        else:
            # In other cases we get <branch>
            return KNOWN_BRANCHES[commit_parent.split()[-1]]

    raise ParentBranchNotFound("Could not determine tracking branch")


# TODO: Reuse the code from infra.py once we move bugzilla
#  related code to a separate module
def get_connection_params(conf_file_name):
    conf_file = os.path.join(Path(".").resolve(), conf_file_name)
    parser = ConfigParser()
    # Open the file with the correct encoding
    parser.read(conf_file, encoding="utf-8")
    params_dict = {}
    for params in parser.items("DEFAULT"):
        params_dict[params[0]] = params[1]
    return params_dict


def get_bug(bug_id):
    bugzilla_connection_params = get_connection_params(conf_file_name="bugzilla.cfg")
    bzapi = bugzilla.Bugzilla(
        url=bugzilla_connection_params["bugzilla_url"],
        user=bugzilla_connection_params["bugzilla_username"],
        api_key=bugzilla_connection_params["bugzilla_api_key"],
    )
    try:
        return bzapi.getbug(objid=bug_id)
    except Fault:
        print(f"Failed to get bug {bug_id}")


def all_python_files():
    exclude_dirs = [".tox"]
    for root, _, files in os.walk(os.path.abspath(os.curdir)):
        if [_dir for _dir in exclude_dirs if _dir in root]:
            continue

        for filename in files:
            if filename.endswith(".py") and filename != os.path.split(__file__)[-1]:
                yield os.path.join(root, filename)


def get_all_bugs_from_file(file_content):
    """
    Try to find all bugs in the file.
    Looking for the following patterns:
    - bug_id=12345  # call in is_bug_open
    - bug_id = 12345  # when bug is constant
    - https://bugzilla.redhat.com/show_bug.cgi?id=12345  # when bug is in a link in comments
    - pytest.mark.bugzilla(12345)  # when bug is in a marker

    Args:
        file_content (str): The content of the file.

    Returns:
        list: A list of bugs.
    """
    _pytest_bugzilla_marker_bugs = re.findall(
        r"pytest.mark.bugzilla.*?(\d{7,})", file_content, re.DOTALL
    )
    _is_bug_open_bugs = re.findall(r"(?:bug_id=|.*bug.* = )(\d{7,})", file_content)
    _bugzilla_url_bugs = re.findall(
        r"https://bugzilla.redhat.com/show_bug.cgi\?id=(\d{7,}(?! <skip-bug-check>))",
        file_content,
    )
    return set(_pytest_bugzilla_marker_bugs + _is_bug_open_bugs + _bugzilla_url_bugs)


def main():
    parent_branch = get_parent_branch()
    closed_bugs = {}
    mismatch_bugs_version = {}
    for filename in all_python_files():
        filename_for_key = re.findall(r"cnv-tests/.*", filename)[0]
        with open(filename, "r") as fd:
            for _bug in get_all_bugs_from_file(file_content=fd.read()):
                bug = get_bug(bug_id=_bug)
                bug_status = bug.status
                if bug_status in BUG_STATUS_CLOSED:
                    closed_bugs.setdefault(filename_for_key, []).append(
                        f"{_bug} [{bug_status}]"
                    )

                else:
                    bug_target_release = bug.target_release[0]
                    try:
                        bug_target_release_version = Version(bug_target_release)
                        if bug_target_release_version > Version(
                            KNOWN_BRANCHES["master"]
                        ):
                            continue

                    except InvalidVersion:
                        # Continue if target version is not version.
                        continue

                    if parent_branch not in bug_target_release:
                        mismatch_bugs_version.setdefault(filename_for_key, []).append(
                            f"{_bug} [{bug_status}] [{bug_target_release}]"
                        )

    if closed_bugs:
        print(
            f"The following bugs are closed and needs to be removed ({len(closed_bugs)}):"
        )
        print_status(status_dict=closed_bugs)

    if mismatch_bugs_version:
        print(
            f"The following bugs are not matched the current branch {parent_branch} "
            f"and needs to be removed ({len(mismatch_bugs_version)}):"
        )
        print_status(status_dict=mismatch_bugs_version)

    if closed_bugs or mismatch_bugs_version:
        exit(1)


if __name__ == "__main__":
    main()
