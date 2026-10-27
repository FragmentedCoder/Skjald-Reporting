"""The renderer: turns files from outside into pages, with no way out.

It runs as a service of its own (the app's image as `python -m app.renderer`) with no
network at all, a read-only filesystem, no capabilities, and limits on memory, CPU
and processes (deploy/docker-compose.yml); each conversion also runs under its own
limits and time. It shares one folder, kept in memory, with the worker: the worker
leaves a job there, the renderer leaves the result beside it and removes the job.
Nothing else reaches it, so a hostile file can't reach anything either.

Phase 2 converts customers' report backgrounds: an A4 PDF's first two pages become
SVG (poppler's pdftocairo draws text as shapes, so no fonts travel), the first for a
report's first page and the second for the rest. Phase 3 adds rendering reports.
"""

from __future__ import annotations

import json
import logging
import os
import re
import resource
import subprocess
import tempfile
import time
from pathlib import Path

log = logging.getLogger("skjald.renderer")

EXCHANGE = Path(os.environ.get("SKJALD_EXCHANGE_DIR", "/exchange"))
A4_POINTS = (595.28, 841.89)
MAX_PAGES = 2
TIME_LIMIT = 30
POINTS_PER_MM = 72 / 25.4


class RenderError(ValueError):
    """The file can't be used; the message is fit to show."""


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (TIME_LIMIT, TIME_LIMIT))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))


def _run(*command: str) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=TIME_LIMIT,
                              preexec_fn=_limits, check=False)
    except subprocess.TimeoutExpired:
        raise RenderError("The PDF took too long to read.") from None
    if done.returncode != 0:
        raise RenderError("That file isn't a PDF Skjald can read.")
    return done.stdout


def page_sizes(pdf: Path) -> list[tuple[float, float]]:
    """The width and height in points of the first pages."""
    info = _run("pdfinfo", "-f", "1", "-l", str(MAX_PAGES), str(pdf))
    sizes = [(float(w), float(h)) for w, h in
             re.findall(r"^Page\s+\d+\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", info, re.M)]
    if not sizes:
        raise RenderError("That file isn't a PDF Skjald can read.")
    return sizes


def convert_background(pdf: Path) -> list[str]:
    """The first one or two pages of an A4 portrait PDF, as SVG."""
    sizes = page_sizes(pdf)
    width, height = sizes[0]
    if abs(width - A4_POINTS[0]) > 6 or abs(height - A4_POINTS[1]) > 6:
        raise RenderError(
            f"The background must be A4 portrait (210 × 297 mm); its first page is "
            f"{width / POINTS_PER_MM:.0f} × {height / POINTS_PER_MM:.0f} mm.")
    pages = []
    with tempfile.TemporaryDirectory() as work:
        for number in range(1, len(sizes) + 1):
            out = Path(work) / f"page-{number}.svg"
            _run("pdftocairo", "-svg", "-f", str(number), "-l", str(number), str(pdf), str(out))
            pages.append(out.read_text())
    return pages


def _handle(job: Path) -> None:
    out = EXCHANGE / "out" / f"{job.stem}.json"
    try:
        result: dict[str, object] = {"pages": convert_background(job)}
    except RenderError as exc:
        result = {"error": str(exc)}
    except Exception:  # anything else is reported, never left to hang the worker
        log.exception("Converting %s failed", job.name)
        result = {"error": "The file couldn't be converted."}
    partial = out.with_suffix(".part")
    partial.write_text(json.dumps(result))
    partial.rename(out)
    job.unlink(missing_ok=True)


def serve() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for folder in ("in", "out"):
        (EXCHANGE / folder).mkdir(parents=True, exist_ok=True)
    log.info("Renderer started.")
    while True:
        for job in sorted((EXCHANGE / "in").glob("*.pdf")):
            _handle(job)
        time.sleep(0.3)


if __name__ == "__main__":
    serve()
