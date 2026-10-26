#!/usr/bin/env bash
# Tests for install.sh's functions, without root, Docker or a real /etc/skjald:
#   deploy/install.test.sh
set -euo pipefail

WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT
export SKJALD_ETC="${WORK}/etc" ENV_FILE="${WORK}/.env"
mkdir -p "${SKJALD_ETC}"
# shellcheck source=deploy/install.sh
. "$(dirname "$0")/install.sh"
set +e # the tests look at failures themselves
APP_UID=$(id -u)

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

# A key as the kit writes it: base32 in groups of four (here in lower case).
head -c 32 /dev/urandom >"${WORK}/key"
kit=$(base32 -w0 "${WORK}/key" | tr -d '=' | sed 's/..../& /g' | tr '[:upper:]' '[:lower:]')
other=$(head -c 32 /dev/urandom | base32 -w0 | tr -d '=')

decodes() { kit_to_key "$1" "${WORK}/decoded" >/dev/null && cmp -s "${WORK}/key" "${WORK}/decoded"; }
refused() { ! kit_to_key "$1" "${WORK}/decoded" >/dev/null; }
check "a kit key decodes to its 32 bytes" decodes "${kit}"
check "dashes and capitals are forgiven" decodes "${kit// /-}"
check "a key a group short is refused" refused "${kit:0:60}"
check "letters outside base32 are refused" refused "1${kit:1}"
check "the refusal says what a kit key looks like" \
	grep -q "13 groups" <(kit_to_key "${kit:0:60}" /dev/null)

restores() { (KIT_MASTER_KEY=$1 restore_master_key) 2>&1; }
in_place() { cmp -s "${WORK}/key" "${SKJALD_ETC}/master.key"; }
owner_only() { [[ $(stat -c %a "${SKJALD_ETC}/master.key") == 600 ]]; }
check "the kit's master key goes in place" grep -q "Put the recovery kit's" <(restores "${kit}")
check "  the key is the kit's" in_place
check "  readable only by its owner" owner_only
check "the same key again is fine" grep -q "already in place" <(restores "${kit^^}")
check "a different key is refused" grep -q "A different master key" <(restores "${other}")
check "  and the one in place stays" in_place
generate_master_key >/dev/null
check "a new master key never replaces one" in_place

for good in https://skjald.example.internal https://skjald.example.internal:8443 https://localhost; do
	check "address ${good} is taken" valid_address "${good}"
done
not_valid() { ! valid_address "$1"; }
for bad in http://skjald.example.internal https://skjald.example.internal/ 'https://a b' \
	'https://x;rm -rf /' https://-skjald.example.internal skjald.example.internal; do
	check "address '${bad}' is refused" not_valid "${bad}"
done

configure_address https://skjald.example.internal:8443 >/dev/null
check "the address goes into .env" grep -qx "SKJALD_ADDRESS=https://skjald.example.internal:8443" "${ENV_FILE}"
check "  with its port" grep -qx "SKJALD_HTTPS_PORT=8443" "${ENV_FILE}"
check "an .env with an address is kept" \
	grep -q "Using the address" <(configure_address https://other.example.internal)
check "  unchanged" grep -qx "SKJALD_ADDRESS=https://skjald.example.internal:8443" "${ENV_FILE}"

mkdir -p "${WORK}/bin"
BIN_DIR="${WORK}/bin" link_command >/dev/null
check "the skjald command is linked onto the PATH" \
	test "$(readlink "${WORK}/bin/skjald")" = "${DEPLOY_DIR}/skjald"
check "  and runs" grep -q "keys rotate" <("${WORK}/bin/skjald" help)

# A release's compose file must name its images; one naming none would pass every check.
printf 'services:\n  app:\n    command: ["true"]\n' >"${WORK}/empty-compose.yml"
printf 'services:\n  app:\n    build:\n      context: .\n    image: x@sha256:%s\n' "$(printf 'a%.0s' {1..64})" >"${WORK}/built-compose.yml"
check "a release that names no images is refused" \
	grep -q "names no images" <( (verify_images "${WORK}/empty-compose.yml" v1.0.0) 2>&1)
check "one that builds is refused" \
	grep -q "builds images instead" <( (verify_images "${WORK}/built-compose.yml" v1.0.0) 2>&1)
check "the signer is the release workflow, for that very tag" \
	grep -qx "https://github.com/FragmentedCoder/Skjald-Reporting/.github/workflows/release.yml@refs/tags/v1.2.3" <(signer v1.2.3)
check "something that isn't a release is refused before anything is fetched" \
	grep -q "isn't a release" <( (fetch_release "v1.2; rm -rf /" "${WORK}/fetched") 2>&1)

# As the one-line install runs it: the script on stdin, with no file name.
piped() { bash -s -- "$@" <"$(dirname "$0")/../install.sh" 2>&1; }
check "piped (as curl | sudo bash runs it), it gets to its first real step" \
	grep -q "Run this installer as root" <(piped --address https://skjald.example.internal)
check "  and refuses a bad option plainly" grep -q "Unknown option --nope" <(piped --nope)

if [[ ${failures} -gt 0 ]]; then
	echo "${failures} failed."
	exit 1
fi
echo "All passed."
