"""Compare results/*.json against the expectations in cases.json and print a Markdown table."""

import json
import math
import pathlib

HERE = pathlib.Path(__file__).parent
SPEC = json.loads((HERE / "cases.json").read_text())
ENGINES = [name for name in ("google", "js", "celpy") if (HERE / "results" / f"{name}.json").exists()]
RESULTS = {name: {r["id"]: r for r in json.loads((HERE / "results" / f"{name}.json").read_text())}
           for name in ENGINES}


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b)
    return a == b


def verdict(case, result) -> tuple[bool, str]:
    limit = case.get("time_limit_ms")
    if limit and result["ms"] > limit:
        return False, f"too slow: {result['ms']:.0f} ms"
    if case.get("expect_error"):
        return (True, "error, as expected") if result["error"] else (False, f"no error: {result['value']!r}")
    if result["error"]:
        return False, result["error"].split("\n")[0][:90]
    if same(result["value"], case["expect"]):
        return True, "ok"
    return False, f"got {result['value']!r}"


def main() -> None:
    header = "| Need | " + " | ".join(ENGINES) + " |"
    print(header)
    print("| --- |" + " --- |" * len(ENGINES))
    totals = {name: 0 for name in ENGINES}
    for case in SPEC["cases"]:
        cells = []
        for name in ENGINES:
            ok, note = verdict(case, RESULTS[name][case["id"]])
            totals[name] += ok
            cells.append(("pass" if ok else "**fail**") + ("" if note == "ok" else f" — {note}"))
        print(f"| {case['need']} | " + " | ".join(cells) + " |")
    count = len(SPEC["cases"])
    print("| **Passed** | " + " | ".join(f"**{totals[n]} / {count}**" for n in ENGINES) + " |")


if __name__ == "__main__":
    main()
