#!/usr/bin/env bash
# Tests for the skjald command's own logic, without Docker:  deploy/skjald.test.sh
# (what it does with Docker is tried against a real stack).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT

failures=0
check() {
	local name=$1
	shift
	if "$@"; then
		printf 'ok    %s\n' "${name}"
	else
		printf 'FAIL  %s\n' "${name}"
		failures=$((failures + 1))
	fi
}

# A checkout of its own, with the command in its deploy folder.
mkdir -p "${WORK}/repo/deploy"
cp "${HERE}/skjald" "${WORK}/repo/deploy/skjald"
git -C "${WORK}/repo" init --quiet
git -C "${WORK}/repo" -c user.name=t -c user.email=t@example.invalid commit --quiet --allow-empty -m start
skjald() { SKJALD_HOME="${WORK}/home" "${WORK}/repo/deploy/skjald" "$@"; }

for command in status logs "start | stop | restart" backup restore-test restore update "keys rotate" \
	"admin reset-allowlist" "admin reset-certificate" setup-token; do
	check "help lists ${command}" grep -q "^  ${command}" <(skjald help)
done
unknown() { ! skjald format-disk >/dev/null 2>&1 && [[ $(skjald format-disk 2>&1 >/dev/null | head -1) == Usage* ]]; }
check "an unknown command shows the usage and fails" unknown
check "keys says how it's used" grep -q "Usage: skjald keys rotate" <(skjald keys spin 2>&1 || true)
check "admin says what there is" grep -q "reset-allowlist | reset-certificate" <(skjald admin nuke 2>&1 || true)

# shellcheck source=deploy/skjald
. "${WORK}/repo/deploy/skjald"
set +e
check "with no .env, the address is localhost" test "$(address)" = "https://localhost"
printf 'SKJALD_ADDRESS=https://skjald.example.internal:8443\n' >"${WORK}/repo/deploy/.env"
check "the address comes from .env" test "$(address)" = "https://skjald.example.internal:8443"
check "the version names the commit" grep -qE '^Skjald [0-9a-f]{7,} \([0-9]{4}-[0-9]{2}-[0-9]{2}\)$' <(version)
printf 'v1.2.3\n' >"${WORK}/repo/deploy/VERSION"
check "installed from a release, the version is the release's" test "$(version)" = "Skjald v1.2.3"
check "  and update knows it" from_release
rm "${WORK}/repo/deploy/VERSION"

touch "${WORK}/repo/stray-file"
check "update refuses a checkout with changes of its own" \
	grep -q "has changes of its own" <(skjald update 2>&1 || true)
check "  before touching the data" test ! -e "${WORK}/home/rollback/data-"*

if [[ ${failures} -gt 0 ]]; then
	echo "${failures} failed."
	exit 1
fi
echo "All passed."
