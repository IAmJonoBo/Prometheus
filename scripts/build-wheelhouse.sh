#!/usr/bin/env bash
#
# build-wheelhouse.sh - Pre-download project dependencies for offline installs.
#
# This script exports the Poetry dependency graph and downloads wheels into a
# wheelhouse directory so that environments without egress (for example, GitHub
# Copilot workspaces or locked-down CI runners) can bootstrap virtualenvs.
#
# Usage:
#   scripts/build-wheelhouse.sh [wheelhouse-dir]
#
# Environment variables:
#   POETRY           Path to the poetry executable (default: poetry in PATH)
#   PYTHON_BIN       Python interpreter to invoke (default: auto-detected)
#   EXTRAS           Comma-separated extras to include (e.g. "pii")
#   INCLUDE_DEV      When "true", include dev dependencies (default: false)
#   CREATE_ARCHIVE   When "true", package the wheelhouse as wheelhouse.tar.gz
#
# The resulting directory will contain a requirements.txt file and cached
# wheels. Copy the directory (or archive) alongside the repository and install
# with:
#   python -m pip install --no-index --find-links <wheelhouse> -r requirements.txt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
POETRY_BIN="${POETRY:-poetry}"
WHEELHOUSE="${1:-${REPO_ROOT}/vendor/wheelhouse}"
REQ_FILE="${WHEELHOUSE}/requirements.txt"
EXTRAS_LIST="${EXTRAS-}"
INCLUDE_DEV="${INCLUDE_DEV:-false}"
CREATE_ARCHIVE="${CREATE_ARCHIVE:-false}"
PYTHON_CANDIDATES=("python3" "python")

if [[ -n ${PYTHON_BIN:-} ]]; then
        read -r -a PYTHON_CMD <<<"${PYTHON_BIN}"
else
        for candidate in "${PYTHON_CANDIDATES[@]}"; do
                if command -v "${candidate}" >/dev/null 2>&1; then
                        PYTHON_CMD=("${candidate}")
                        break
                fi
        done
        if [[ ${#PYTHON_CMD[@]} -eq 0 ]] && command -v py >/dev/null 2>&1; then
                PYTHON_CMD=("py" "-3")
        fi
        if [[ ${#PYTHON_CMD[@]} -eq 0 ]]; then
                printf >&2 'Unable to locate a Python interpreter. Set PYTHON_BIN to override.\n'
                exit 1
        fi
fi

to_lower() {
	printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}
ARCHIVE_PATH="${WHEELHOUSE}.tar.gz"

# Start fresh to avoid stale files from previous runs.
rm -rf "${WHEELHOUSE}"
mkdir -p "${WHEELHOUSE}"

EXPORT_ARGS=("--without-hashes")
if [[ -n ${EXTRAS_LIST} ]]; then
	IFS=',' read -ra extras_array <<<"${EXTRAS_LIST}"
	for extra in "${extras_array[@]}"; do
		extra_trimmed="${extra// /}"
		if [[ -n ${extra_trimmed} ]]; then
			EXPORT_ARGS+=("--extras" "${extra_trimmed}")
		fi
	done
fi
if [[ $(to_lower "${INCLUDE_DEV}") == "true" ]]; then
	EXPORT_ARGS+=("--with" "dev")
fi

printf 'Exporting dependency graph with poetry (%s)\n' "${POETRY_BIN}"
"${POETRY_BIN}" export "${EXPORT_ARGS[@]}" -o "${REQ_FILE}"

printf 'Downloading wheels into %s\n' "${WHEELHOUSE}"
"${PYTHON_CMD[@]}" -m pip download --dest "${WHEELHOUSE}" --requirement "${REQ_FILE}"

if [[ $(to_lower "${CREATE_ARCHIVE}") == "true" ]]; then
	printf 'Creating archive %s\n' "${ARCHIVE_PATH}"
	tar -czf "${ARCHIVE_PATH}" -C "${WHEELHOUSE}" .
fi

printf 'Wheelhouse ready: %s\n' "${WHEELHOUSE}"
if [[ $(to_lower "${CREATE_ARCHIVE}") == "true" ]]; then
	printf 'Archive created at: %s\n' "${ARCHIVE_PATH}"
fi
