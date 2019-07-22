# -*- coding: utf-8 -*-

"""
flake8 extension check that every test has Polarion ID attach to it.
"""

import ast
import re

PID001 = "PID001: [{f_name} ({params})], Polarion ID is missing"
PID002 = "PID002: [{f_name} {pid}], Polarion ID is wrong"


def iter_test_functions(tree):
    """
    Get all test function from python file
    """

    def is_test(elm):
        return elm.name.startswith("test_")

    def is_func(elm):
        return isinstance(elm, ast.FunctionDef)

    for elm in tree.body:
        if isinstance(elm, ast.ClassDef):
            for cls_elm in elm.body:
                if is_func(cls_elm) and is_test(cls_elm):
                    yield cls_elm

        elif is_func(elm) and is_test(elm):
            yield elm


def find_func_in_tree(tree, name):
    for elm in tree.body:
        if isinstance(elm, ast.FunctionDef):
            if elm.name == name:
                return elm


def iter_polarion_ids_from_pytest_fixture(tree, name):
    func = find_func_in_tree(tree, name)
    if func:
        if not func.decorator_list:
            return None

        for deco in func.decorator_list:
            if not hasattr(deco, "func"):
                continue

            if deco.func.value.id == "pytest" and deco.func.attr == "fixture":
                for deco_keyword in deco.keywords:
                    if deco_keyword.arg == "params":
                        for deco_elts in deco_keyword.value.elts:
                            has_polarion_id = False
                            for deco_elts_keyword in deco_elts.keywords:
                                if (
                                    deco_elts_keyword.arg == "marks"
                                    and deco_elts_keyword.value.func.attr == "polarion"
                                ):
                                    has_polarion_id = True
                                    yield deco_elts_keyword.value.args[0]
                            if not has_polarion_id:
                                yield deco_elts


class PolarionIds(object):
    """
    flake8 extension check that every test has Polarion ID attach to it.
    """

    name = "PolarionIds"
    version = "1.0.0"

    def __init__(self, tree):
        self.tree = tree

    def _non_decorated(self, f, params=""):
        yield (
            f.lineno,
            f.col_offset,
            PID001.format(f_name=f.name, params=params),
            self.name,
        )

    def _non_decorated_elt(self, f, elt, params=""):
        yield (
            elt.lineno,
            elt.col_offset,
            PID001.format(f_name=f.name, params=params),
            self.name,
        )

    def _if_bad_pid(self, f, polarion_id):
        if not re.match(r"CNV-\d+", polarion_id):
            yield (
                f.lineno,
                f.col_offset,
                PID002.format(f_name=f.name, pid=polarion_id),
                self.name,
            )

    def _non_decorated_fixture(self, f, polarion_id):
        param = ""
        if isinstance(polarion_id, ast.Call):
            if isinstance(polarion_id.args[0], ast.Str):
                param = polarion_id.args[0].s
            else:
                param = polarion_id.args[0].elts[0].s

        yield (
            polarion_id.lineno,
            polarion_id.col_offset,
            PID001.format(f_name=f.name, params=param),
            self.name,
        )

    def _if_bad_pid_fixture(self, f, polarion_id):
        if not re.match(r"CNV-\d+", polarion_id.s):
            yield (
                polarion_id.lineno,
                polarion_id.col_offset,
                PID002.format(f_name=f.name, pid=polarion_id.s),
                self.name,
            )

    def _check_pytest_fixture_polarion_ids(self, f):
        has_polarion_id = False
        for f_arg in f.args.args:
            for polarion_id in iter_polarion_ids_from_pytest_fixture(
                self.tree, f_arg.arg
            ):
                if isinstance(polarion_id, ast.Str):
                    has_polarion_id = True
                    yield from self._if_bad_pid_fixture(f, polarion_id)
                else:
                    yield from self._non_decorated_fixture(f, polarion_id)
        if not has_polarion_id:
            yield from self._non_decorated(f, "")

    def run(self):
        """
        Check that every test has a Polarion ID
        """
        for f in iter_test_functions(self.tree):
            if not f.decorator_list:
                # Test is missing Polarion ID, check if test use parametrize fixture
                # with Polarion ID.
                yield from self._check_pytest_fixture_polarion_ids(f)

            for deco in f.decorator_list:
                if not hasattr(deco, "func"):
                    continue

                if (
                    deco.func.value.value.id == "pytest"
                    and deco.func.value.attr == "mark"
                ):
                    if deco.func.attr == "polarion":
                        if deco.args:
                            yield from self._if_bad_pid(f, deco.args[0].s)
                        else:
                            yield from self._non_decorated(f)

                    elif deco.func.attr == "parametrize":
                        if deco.args:
                            for arg in deco.args:
                                if not isinstance(arg, ast.List):
                                    continue

                                for elt in arg.elts:
                                    if not isinstance(elt, ast.Call):
                                        yield from self._non_decorated_elt(
                                            f, elt, elt.s
                                        )
                                        continue

                                    if not elt.keywords:
                                        yield from self._non_decorated_elt(f, elt)

                                    for pk in elt.keywords:
                                        # In case of multiple marks on test param
                                        if isinstance(pk.value, ast.Tuple):
                                            for elt_val in pk.value.elts:
                                                if elt_val.func.attr == "polarion":
                                                    yield from self._if_bad_pid(
                                                        f, elt_val.args[0].s
                                                    )

                                        # In case one mark on test param
                                        elif (
                                            pk.arg == "marks"
                                            and pk.value.func.attr == "polarion"
                                        ):
                                            yield from self._if_bad_pid(
                                                f, pk.value.args[0].s
                                            )
                                            continue
                                        else:
                                            # In case no mark on test param
                                            yield from self._non_decorated(
                                                f, elt.args[0].s
                                            )
                else:
                    yield from self._non_decorated(f, "")
