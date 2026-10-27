"""Tests for the release's compose file:  python3 deploy/release-compose.test.py"""

import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("release_compose", HERE / "release-compose.py")
release_compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_compose)

APP = "ghcr.io/fragmentedcoder/skjald-app@sha256:" + "a" * 64
CADDY = "ghcr.io/fragmentedcoder/skjald-caddy@sha256:" + "b" * 64
compose = (HERE / "docker-compose.yml").read_text()
failures = 0


def check(name: str, ok: bool) -> None:
    global failures
    print(("ok    " if ok else "FAIL  ") + name)
    failures += not ok


made = release_compose.release_compose(compose, APP, CADDY)
local = "localhost:5000/skjald-app@sha256:" + "d" * 64
check("a registry with a port will do", local in release_compose.release_compose(compose, local, CADDY))
check("no service is built", "build:" not in made)
check("the app, worker, renderer and tools run the app image", made.count(f"image: {APP}") == 4)
check("Caddy runs the Caddy image", made.count(f"image: {CADDY}") == 1)
check("the version is the image's own, not a setting", "SKJALD_VERSION" not in made)
check("the rest is as it was", made.count("SKJALD_ETC") == compose.count("SKJALD_ETC"))
for bad in ("ghcr.io/fragmentedcoder/skjald-app:v1.0.0", "evil\nimage: x@sha256:" + "c" * 64):
    try:
        release_compose.release_compose(compose, bad, CADDY)
        check(f"refuses {bad!r}", False)
    except SystemExit:
        check(f"refuses {bad!r}", True)
try:
    release_compose.release_compose(compose.replace("context: ../backend", "context: ../app"),
                                    APP, CADDY)
    check("notices a build block it doesn't know", False)
except SystemExit:
    check("notices a build block it doesn't know", True)

print("All passed." if not failures else f"{failures} failed.")
sys.exit(1 if failures else 0)
