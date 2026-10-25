#!/bin/sh
# Caddy, with the TLS settings the app writes into the volume shared at
# /etc/caddy/skjald (see backend/app/tls.py and docs/architecture.md, "HTTPS").
# They're copied into place, and Caddy reloads whenever they change; settings
# that don't load leave Caddy with the ones it had.
set -u

shared=/etc/caddy/skjald
active=/etc/caddy/active-tls.caddy
config="--config /etc/caddy/Caddyfile --adapter caddyfile"

fingerprint() {
	cat "$shared/tls.caddy" "$shared/cert.pem" "$shared/key.pem" 2>/dev/null | sha256sum
}

take_shared() {
	if [ -s "$shared/tls.caddy" ]; then
		cp "$shared/tls.caddy" "$active"
	else
		cp /etc/caddy/default-tls.caddy "$active"
	fi
}

seen=$(fingerprint)
take_shared
# shellcheck disable=SC2086
if ! caddy validate $config >/dev/null 2>&1; then
	echo "The saved TLS settings don't load: serving Caddy's own certificate." >&2
	cp /etc/caddy/default-tls.caddy "$active"
fi

# shellcheck disable=SC2086
caddy run $config &
caddy_pid=$!
trap 'kill -TERM "$caddy_pid" 2>/dev/null' TERM INT

while kill -0 "$caddy_pid" 2>/dev/null; do
	sleep 5 &
	wait $!
	now=$(fingerprint)
	[ "$now" = "$seen" ] && continue
	seen=$now
	cp "$active" "$active.before"
	take_shared
	# --force: a new certificate under the same file names is still a change.
	# shellcheck disable=SC2086
	if caddy reload $config --force; then
		echo "The TLS settings changed: Caddy reloaded."
	else
		echo "The new TLS settings didn't load: Caddy keeps the ones it had." >&2
		mv "$active.before" "$active"
	fi
done
wait "$caddy_pid"
