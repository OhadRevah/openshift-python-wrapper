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


class PolarionIds(object):
    """
    flake8 extension check that every test has Polarion ID attach to it.
    """
    name = 'PolarionIds'
    version = '1.0.0'

    def __init__(self, tree):
        self.tree = tree

    def _non_decorated(self, f, params=''):
        yield (
            f.lineno,
            f.col_offset,
            PID001.format(f_name=f.name, params=params),
            self.name)

    def _non_decorated_elt(self, f, elt, params=''):
        yield (
            elt.lineno,
            elt.col_offset,
            PID001.format(f_name=f.name, params=params),
            self.name)

    def _if_non_cnv(self, f, deco):
        if deco.args:
            if not re.match(r'CNV-\d+', deco.args[0].s):
                yield (
                    f.lineno,
                    f.col_offset,
                    PID002.format(f_name=f.name, pid=deco.args[0].s),
                    self.name)

    def run(self):
        """
        Check that every test has a Polarion ID
        """
        for f in iter_test_functions(self.tree):
            if not f.decorator_list:
                yield from self._non_decorated(f)

            for deco in f.decorator_list:
                if not hasattr(deco, 'func'):
                    continue

                if deco.func.value.value.id == 'pytest' and deco.func.value.attr == 'mark':
                    if deco.func.attr == 'polarion':
                        yield from self._if_non_cnv(f, deco)

                    elif deco.func.attr == 'parametrize':
                        if deco.args:
                            for arg in deco.args:
                                if not isinstance(arg, ast.List):
                                    continue

                                for elt in arg.elts:
                                    if not isinstance(elt, ast.Call):
                                        yield from self._non_decorated_elt(f, elt, elt.s)
                                        continue

                                    if not elt.keywords:
                                        elt_s = elt.args[0].s if isinstance(elt, ast.Call) else elt.s
                                        yield from self._non_decorated_elt(f, elt, elt_s)

                                    for pk in elt.keywords:
                                        # In case of multiple marks on test param
                                        if isinstance(pk.value, ast.Tuple):
                                            for elt_val in pk.value.elts:
                                                if elt_val.func.attr == 'polarion':
                                                    yield from self._if_non_cnv(f, elt_val)

                                        # In case one mark on test param
                                        elif pk.arg == 'marks' and pk.value.func.attr == 'polarion':
                                            if pk.value:
                                                yield from self._if_non_cnv(f, pk.value)
                                                continue
                                        else:
                                            # In case no mark on test param
                                            yield from self._non_decorated(f, elt.args[0].s)
                else:
                    yield from self._non_decorated(f)
