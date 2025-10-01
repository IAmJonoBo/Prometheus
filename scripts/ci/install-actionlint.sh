#!/usr/bin/env bash
set -euo pipefail

# install-actionlint.sh - Ensure a portable actionlint binary is available.
# Prefers a pre-seeded offline binary under vendor/tooling/actionlint.
# Falls back to downloading the official release when network access is allowed.

VERSION="1.7.7"
PLATFORM="linux_amd64"
ARCHIVE="actionlint_${VERSION}_${PLATFORM}.tar.gz"
FALLBACK_DIR="${RUNNER_TEMP:-/tmp}/actionlint-${VERSION}"
VENDORED_BIN="$(pwd)/vendor/tooling/actionlint"

# Helper to register environment variables for downstream steps.
register_path() {
	local bin_path=$1
	chmod +x "$bin_path"
	echo "ACTIONLINT_BIN=${bin_path}" >>"${GITHUB_ENV}"
	echo "actionlint-bin=${bin_path}" >>"${GITHUB_OUTPUT:-/dev/null}"
}

if [ -x "${VENDORED_BIN}" ]; then
	echo "Using vendored actionlint binary at ${VENDORED_BIN}" >&2
	register_path "${VENDORED_BIN}"
	exit 0
fi

mkdir -p "${FALLBACK_DIR}"
ARCHIVE_PATH="${FALLBACK_DIR}/${ARCHIVE}"
BIN_PATH="${FALLBACK_DIR}/actionlint"

if [ ! -x "${BIN_PATH}" ]; then
	echo "Vendored actionlint not found; attempting to download release v${VERSION}" >&2
	curl -fsSL "https://github.com/rhysd/actionlint/releases/download/v${VERSION}/${ARCHIVE}" -o "${ARCHIVE_PATH}"
	tar -xzf "${ARCHIVE_PATH}" -C "${FALLBACK_DIR}"
fi

register_path "${BIN_PATH}"
