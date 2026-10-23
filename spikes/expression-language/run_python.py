"""Run cases.json through the Python CEL engines and write results/<engine>.json.

Engines:
  google   cel-expr-python, Google's official wrapper around the C++ CEL engine
  celpy    cel-python, a community pure-Python implementation (for comparison)

Both get the same custom functions: xor, switch, re_match and re_replace (RE2), sum, lookup.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import re2  # google-re2: linear-time regular expressions, the same semantics as CEL's matches()

HERE = pathlib.Path(__file__).parent
SPEC = json.loads((HERE / "cases.json").read_text())
TABLES = SPEC["lookup_tables"]


def plain(value):
    """Turn engine values into plain JSON-able Python values."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return str(value)


# ----------------------------------------------------------------------------- shared custom functions


def fn_xor(a, b):
    return bool(a) != bool(b)


def fn_switch(value, cases, default):
    return cases[value] if value in cases else default


def fn_re_match(text, pattern):
    return re2.search(str(pattern), str(text)) is not None


def fn_re_replace(text, pattern, replacement):
    return re2.sub(str(pattern), str(replacement), str(text))


def fn_sum(items):
    return sum(items)


def fn_lookup(table, key):
    return TABLES[str(table)][str(key)]


# ----------------------------------------------------------------------------- google: cel-expr-python


def google_engine():
    from cel_expr_python import cel
    from cel_expr_python.ext import ext_strings

    T = cel.Type
    functions = [
        cel.FunctionDecl("xor", [cel.Overload("xor_bool_bool", T.BOOL, [T.BOOL, T.BOOL], impl=fn_xor)]),
        # The Python wrapper needs concrete types for custom functions (DYN parameters never match),
        # so each type combination Skjald needs gets its own overload.
        cel.FunctionDecl("switch", [
            cel.Overload("switch_string_string", T.STRING, [T.STRING, T.Map(T.STRING, T.STRING), T.STRING],
                         impl=fn_switch),
            cel.Overload("switch_int_string", T.STRING, [T.INT, T.Map(T.INT, T.STRING), T.STRING],
                         impl=fn_switch),
        ]),
        cel.FunctionDecl("re_match", [cel.Overload("re_match_string", T.BOOL, [T.STRING, T.STRING],
                                                   impl=fn_re_match)]),
        cel.FunctionDecl("re_replace", [cel.Overload("re_replace_string", T.STRING,
                                                     [T.STRING, T.STRING, T.STRING], impl=fn_re_replace)]),
        cel.FunctionDecl("sum", [cel.Overload("sum_list", T.DYN, [T.List(T.DYN)], impl=fn_sum)]),
        cel.FunctionDecl("lookup", [cel.Overload("lookup_string_string", T.STRING, [T.STRING, T.STRING],
                                                 impl=fn_lookup)]),
    ]

    def run(case):
        env = cel.NewEnv(variables={name: T.DYN for name in case["vars"]},
                         extensions=[ext_strings.ExtStrings()], functions=functions)
        result = env.compile(case["expr"]).eval(data=case["vars"])
        if result.type() == T.ERROR:  # the C++ engine returns errors as values
            raise RuntimeError(str(result.value()))
        return plain(result.value())

    return run


# ----------------------------------------------------------------------------- celpy: cel-python


def celpy_engine():
    import celpy
    from celpy.evaluation import CELEvalError

    def wrap(fn):
        def call(*args):
            result = fn(*[plain(a) for a in args])
            return celpy.json_to_cel(result)
        return call

    functions = {"xor": wrap(fn_xor), "switch": wrap(fn_switch), "re_match": wrap(fn_re_match), "re_replace": wrap(fn_re_replace),
                 "sum": wrap(fn_sum), "lookup": wrap(fn_lookup)}

    def run(case):
        env = celpy.Environment()
        program = env.program(env.compile(case["expr"]), functions=functions)
        result = program.evaluate({k: celpy.json_to_cel(v) for k, v in case["vars"].items()})
        if isinstance(result, (CELEvalError, Exception)):
            raise RuntimeError(str(result))
        return plain(result)

    return run


ENGINES = {"google": google_engine, "celpy": celpy_engine}


def main(names: list[str]) -> None:
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    for name in names:
        run = ENGINES[name]()
        results = []
        for case in SPEC["cases"]:
            start = time.perf_counter()
            try:
                value, error = run(case), None
            except Exception as exc:  # record the failure, keep going
                value, error = None, f"{type(exc).__name__}: {exc}"[:300]
            results.append({"id": case["id"], "value": value, "error": error,
                            "ms": round((time.perf_counter() - start) * 1000, 2)})
        (out / f"{name}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"{name}: {len(results)} cases run")


if __name__ == "__main__":
    main(sys.argv[1:] or list(ENGINES))
