import ast
import os
import re
import subprocess
import sys

import urllib3
from git import Repo
from pygerrit2 import Anonymous, GerritRestAPI


urllib3.disable_warnings()


def all_python_files():
    exclude_dirs = [".tox"]
    for root, _, files in os.walk(os.path.abspath(os.curdir)):
        if [_dir for _dir in exclude_dirs if _dir in root]:
            continue

        for filename in files:
            if filename.endswith(".py") and filename != os.path.split(__file__)[-1]:
                yield os.path.join(root, filename)


def is_fixture_autouse(func):
    if func.decorator_list:
        for deco in func.decorator_list:
            if not hasattr(deco, "func"):
                continue

            if deco.func.attr == "fixture" and deco.func.value.id == "pytest":
                for _key in deco.keywords:
                    if _key.arg == "autouse":
                        return _key.value.s


def _iter_functions(tree):
    """
    Get all function from python file
    """

    def is_func(_elm):
        return isinstance(_elm, ast.FunctionDef)

    def is_test(_elm):
        return _elm.name.startswith("test_")

    for elm in tree.body:
        if is_func(_elm=elm):
            if is_test(_elm=elm):
                continue

            yield elm


def get_unused_functions():
    _unused_functions = []
    func_ignore_prefix = ["pytest_"]
    for py_file in all_python_files():
        with open(py_file, "r") as fd:
            tree = ast.parse(source=fd.read())

        for func in _iter_functions(tree=tree):
            if [
                func.name
                for ignore_prefix in func_ignore_prefix
                if func.name.startswith(ignore_prefix)
            ]:
                continue

            if is_fixture_autouse(func=func):
                continue

            _used = subprocess.check_output(
                f"git grep -w '{func.name}' | wc -l", shell=True
            )
            used = int(_used.strip())
            if used < 2:
                _unused_functions.append(
                    f"{os.path.relpath(py_file)}:{func.name}:{func.lineno}:{func.col_offset}"
                    f" Is not used anywhere in the code."
                )

    return _unused_functions


def get_change_id_from_commit_msg():
    repo = Repo(path=".")
    commit_msg = repo.commit().message
    return re.findall(r"Change-Id: (.*)", commit_msg)[0]


def is_last_change_in_gerrit_chain():
    should_be_checked = True
    gerrit_url = "https://code.engineering.redhat.com/gerrit"
    gerrit = GerritRestAPI(url=gerrit_url, auth=Anonymous(), verify=False)
    _change_id = get_change_id_from_commit_msg()
    change_branch = gerrit.get(f"/changes/?q={_change_id}")[0]["branch"]

    for open_change in gerrit.get(
        f"/changes/?q=projects:cnv-tests+status:open+branch:{change_branch}"
    ):
        change_submitted_together = gerrit.get(
            f"/changes/{open_change['id']}/submitted_together?"
        )
        for _change in change_submitted_together:
            if _change["change_id"] == _change_id:
                # Check only change if it is the last change in the chain
                if _change["id"] != change_submitted_together[-1]["id"]:
                    should_be_checked = False
    return should_be_checked


if __name__ == "__main__":
    if is_last_change_in_gerrit_chain():
        unused_functions = get_unused_functions()
        if unused_functions:
            print("\n".join(unused_functions))
            sys.exit(1)
