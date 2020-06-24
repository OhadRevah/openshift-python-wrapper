# -*- coding: utf-8 -*-

"""
flake8 plugin which verifies that all functions are called with arg=value (and not only with value).
"""

import ast


FCFN001 = (
    "FCFN001: [{f_name}] function should be called with keywords arguments. {values}"
)


class FunctionCallForceNames(object):
    """
    flake8 plugin which verifies that all functions are called with arg=value (and not only with value).
    """

    name = "FunctionCallForceNames"
    version = "1.0.0"

    def __init__(self, tree):
        self.tree = tree

    @classmethod
    def add_options(cls, option_manager):
        option_manager.add_option(
            "--fcfn_exclude_functions",
            default="",
            parse_from_config=True,
            comma_separated_list=True,
            help="Functions to exclude from checking.",
        )

    @classmethod
    def parse_options(cls, options):
        cls.exclude_functions = options.fcfn_exclude_functions

    def _get_values(self, elm):
        values = ""
        for arg in elm.value.args:
            if isinstance(arg, ast.JoinedStr):
                for val in arg.values:
                    if isinstance(val, ast.FormattedValue):
                        continue

                    values += (
                        f"value: {val.s} (line:{arg.lineno} column:{arg.col_offset})"
                    )
            else:
                values += (
                    f"value: {self._get_elm_func_id(elm_func=arg)} "
                    f"(line:{arg.lineno} column:{arg.col_offset})"
                )
        return values

    def _get_elm_func_id(self, elm_func, attr=False):
        elm_func_id = getattr(elm_func, "id", None)
        if elm_func_id:
            return elm_func_id

        elm_func_s = getattr(elm_func, "s", None)
        if elm_func_s:
            return elm_func_s

        elm_val_func = getattr(elm_func, "func", None)
        if elm_val_func:
            return self._get_elm_func_id(elm_func=elm_val_func, attr=attr)

        if attr:
            elm_func_attr = getattr(elm_func, "attr", None)
            if elm_func_attr:
                return elm_func_attr

        elm_val = getattr(elm_func, "value", None)
        if elm_val:
            return self._get_elm_func_id(elm_func=elm_val, attr=attr)

    def _skip_function_from_check(self, elm):
        name = self._get_elm_func_id(elm_func=elm)
        if name not in self.exclude_functions:
            name = self._get_elm_func_id(elm_func=elm, attr=True)

        return name in self.exclude_functions

    @staticmethod
    def _args_exists(elm):
        if getattr(elm, "value", None):
            args = getattr(elm.value, "args", [])
            for _arg in args:
                if isinstance(_arg, ast.Starred):
                    continue

                return True

    def _missing_keywords(self, func_name, elm):
        if not self._args_exists(elm=elm):
            return

        if self._skip_function_from_check(elm=elm):
            return

        values = self._get_values(elm=elm)
        if values:
            yield (
                elm.value.lineno,
                elm.value.col_offset,
                FCFN001.format(f_name=func_name, values=values),
                self.name,
            )

    def run(self):
        for elm in self.tree.body:
            if isinstance(elm, ast.Expr):
                if isinstance(elm.value, ast.Call):
                    yield from self._missing_keywords(
                        func_name=self._get_elm_func_id(elm), elm=elm,
                    )

            else:
                if not getattr(elm, "body", None):
                    continue

                for elm_body in elm.body:
                    elm_body_value = getattr(elm_body, "value", None)

                    if elm_body_value:
                        if isinstance(elm_body_value, ast.Call):
                            yield from self._missing_keywords(
                                func_name=elm.name, elm=elm_body,
                            )

                    if getattr(elm_body, "body", None):
                        for cls_body in elm_body.body:
                            if isinstance(cls_body, ast.Assign):
                                yield from self._missing_keywords(
                                    func_name=elm.name, elm=cls_body,
                                )
