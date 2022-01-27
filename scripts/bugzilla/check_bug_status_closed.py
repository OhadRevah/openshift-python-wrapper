import os
import re
from configparser import ConfigParser
from pathlib import Path

import bugzilla


BUG_STATUS_CLOSED = ("VERIFIED", "CLOSED", "RELEASE_PENDING")


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


def get_bug_status(bug):
    bugzilla_connection_params = get_connection_params(conf_file_name="bugzilla.cfg")
    bzapi = bugzilla.Bugzilla(
        url=bugzilla_connection_params["bugzilla_url"],
        user=bugzilla_connection_params["bugzilla_username"],
        api_key=bugzilla_connection_params["bugzilla_api_key"],
    )
    return bzapi.getbug(objid=bug).status


if __name__ == "__main__":
    closed_bugs = {}
    for root, dirs, files in os.walk(os.path.abspath(os.curdir)):
        for file in files:
            if not file.endswith(".py") or file in __file__:
                continue

            with open(os.path.join(root, file), "r") as fd:
                data = fd.read()
                _bugs = re.findall(r"@pytest.mark.bugzilla(.*\n.*|.*)", data)
                for _bug in _bugs:
                    bug_id = re.findall(r"\d+", _bug)
                    bug_id = bug_id[0] if bug_id else None
                    if bug_id and get_bug_status(bug=bug_id) in BUG_STATUS_CLOSED:
                        closed_bugs.setdefault(file, []).append(bug_id)

    if closed_bugs:
        print("The following bugs are closed and needs to be removed:")
        for key, value in closed_bugs.items():
            print(f"    {key}:  {' '.join(list(set(value)))}")
        exit(1)
