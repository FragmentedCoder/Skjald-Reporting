FROM python:3.13-slim AS base

# Backups: restic from Debian's signed packages; rclone (for SMB shares; Debian's is
# too old) from its own release, pinned and checked against the SHA-256 in rclone's
# signed checksum list (key FBF737ECE9F8AB18604BD2AC93935E02FF3B54FA).
ARG RCLONE_VERSION=v1.75.2
ARG RCLONE_SHA256_AMD64=349ac8fba6ff65d6247043f1750cdcb518ec5d500ef91463a10d37c0ccdf3702
ARG RCLONE_SHA256_ARM64=7e1e8d69654941b7b7df84ee74c5f7fb09cce7d5496947fb7bf16b55ff427d10
RUN apt-get update \
 && apt-get install -y --no-install-recommends restic ca-certificates curl unzip \
 && arch="$(dpkg --print-architecture)" \
 && case "$arch" in \
      amd64) sum="$RCLONE_SHA256_AMD64" ;; \
      arm64) sum="$RCLONE_SHA256_ARM64" ;; \
      *) echo "No rclone build is pinned for $arch." >&2; exit 1 ;; \
    esac \
 && curl -fsSLo /tmp/rclone.zip \
      "https://downloads.rclone.org/${RCLONE_VERSION}/rclone-${RCLONE_VERSION}-linux-${arch}.zip" \
 && echo "${sum}  /tmp/rclone.zip" | sha256sum -c - \
 && unzip -jq /tmp/rclone.zip "*/rclone" -d /usr/local/bin \
 && chmod 0755 /usr/local/bin/rclone \
 && rm /tmp/rclone.zip \
 && apt-get purge -y curl unzip \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 skjald \
 && useradd --uid 10001 --gid skjald --no-create-home --shell /usr/sbin/nologin skjald

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# /backups: where backups go when the target is this server (a volume, or a folder
# on the host set by SKJALD_BACKUP_DIR). /tls: the TLS settings the app gives Caddy.
RUN mkdir -p /data /backups /tls && chown skjald:skjald /data /backups /tls

USER skjald
EXPOSE 8000

# Trust X-Forwarded-For from any peer: the app port is published to nobody but Caddy
# on the internal network, and Caddy replaces the header for untrusted clients.
# app.setup prints a fresh setup token to the log while setup is pending; app.tls
# gives Caddy the TLS settings that are saved.
CMD ["sh", "-c", "python -m app.migrate && python -m app.setup && python -m app.tls && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
