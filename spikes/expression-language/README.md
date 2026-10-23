# Spike: CEL or SEL for template logic

**Decision: adopt CEL, with a small Skjald function library.** Google's official Python engine (cel-expr-python) passed all 31 test cases on the server. In the browser, cel-js passed every case except its built-in `matches()`, which Skjald replaces with its own RE2-based `re_match()`. Writing our own language (SEL) would add work and a sandbox to maintain, with nothing gained that these tests needed.

## What was tested

`cases.json` holds 31 cases covering every kind of rule asked for: ranges, IF / ELSE IF / ELSE, AND / OR / NOT / XOR, SWITCH, regular expressions, plain and regex text replacement, list checks, sums, lookup tables, missing answers, dates (the NIS2 72-hour deadline), Danish text and emoji, errors, and hostile regular expressions. Each engine runs the same file.

| Engine | Where | Passed |
| --- | --- | --- |
| cel-expr-python 0.1.3 (Google, wraps the C++ engine) | Server | **31 / 31** |
| @marcbachmann/cel-js 8.0.0 + re2js 2.9.0 | Browser | **29 / 31** — both failures are the built-in `matches()` |
| cel-python 0.5.0 (community) | For comparison | 28 / 31 — no string extension, rejects int vs decimal comparison |

Median time per expression, including compiling it: 1.0 ms on the server, 0.3 ms in the browser engine.

<details>
<summary>All 31 cases</summary>

| Need | google | js | celpy |
| --- | --- | --- | --- |
| Value within a range | pass | pass | pass |
| IF / ELSE IF / ELSE | pass | pass | pass |
| AND / OR / NOT | pass | pass | pass |
| XOR without a custom function | pass | pass | pass |
| XOR as a function | pass | pass | pass |
| SWITCH, falling through to the default | pass | pass | pass |
| SWITCH, matching a case | pass | pass | pass |
| SWITCH in plain CEL | pass | pass | pass |
| Built-in matches(): regular expression match | pass | pass | pass |
| Built-in matches(): IPv6 pattern | pass | pass | pass |
| Text replacement with a regular expression | pass | pass | pass |
| Plain text replacement | pass | pass | fail — no `replace` |
| Upper-case text | pass | pass | fail — no `upperAscii` |
| Any item in a list | pass | pass | pass |
| Every item in a list | pass | pass | pass |
| Count matching items | pass | pass | pass |
| Sum a column | pass | pass | pass |
| Lookup table | pass | pass | pass |
| Missing answer gets a default | pass | pass | pass |
| Number into text | pass | pass | pass |
| Whole number compared with a decimal | pass | pass | fail |
| Date arithmetic (NIS2 72-hour deadline passed) | pass | pass | pass |
| Length of Danish text | pass | pass | pass |
| Length of text with an emoji (code points) | pass | pass | pass |
| Errors are errors, not crashes | pass | pass | pass |
| Unknown names are rejected | pass | pass | pass |
| Built-in matches(): non-RE2 syntax rejected | pass | **fail** — accepts `a(?=b)` | pass |
| Built-in matches(): hostile pattern stays fast | pass | **fail** — 1.2 s on 26 characters | pass |
| Skjald re_match(): regular expression match on RE2 | pass | pass | pass |
| Skjald re_match(): non-RE2 syntax rejected on both sides | pass | pass | pass |
| Skjald re_match(): hostile pattern stays fast | pass | pass | pass |

</details>

## Findings for the real build

- **Use Skjald's own regex functions.** cel-js runs `matches()` on JavaScript's regex engine. It accepts syntax the server rejects, and a pattern like `^(a+)+$` takes 1.2 s on 26 characters, doubling with every extra character. cel-js won't let us replace the built-in, so templates use `re_match()` and `re_replace()`, backed by RE2 on both sides (google-re2 on the server, re2js in the browser). The template validator rejects `matches()`.
- **The Skjald function library:** `xor`, `switch`, `re_match`, `re_replace`, `replace` (cel-js lacks it), `sum`, `lookup`, plus date and formatting helpers as needed. Each one is implemented twice and covered by this shared test file, which runs in CI.
- **Declare typed overloads on the server.** Google's Python wrapper needs concrete parameter types for custom functions; an "any" (DYN) parameter never matches. So `switch` has one version for text keys and one for number keys, and so on.
- **The browser preview runs in a Web Worker with a time limit.** RE2 already removes the regex risk, so this is a second guard, and cel-js has no run-time cost limit of its own.
- **People don't need to write CEL.** The visual rule builder writes the expressions. Power users who open the text form see CEL, e.g. `cvss >= 9.0 ? "Critical" : cvss >= 7.0 ? "High" : "Low"`.

## Risks

- cel-expr-python is new (0.1.x, released March 2026) and its repository doesn't take outside contributions yet. Its version is pinned, and this test file runs in CI on every upgrade.
- cel-js has a single maintainer. It's small and MIT-licensed, so forking it is a realistic fallback.
- Templates store CEL text, and the builder hides the syntax. If either engine ever fails us, moving to another engine, or to our own SEL, touches the evaluators but not the templates' structure.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
npm install
.venv/bin/python run_python.py      # writes results/google.json and results/celpy.json
node run_js.mjs                     # writes results/js.json
python compare.py                   # prints the table
```
