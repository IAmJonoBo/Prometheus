#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log() {
	printf '[deps-preflight] %s\n' "$*"
}

cleanup_target() {
	local target="$1"
	if [[ -d ${target} ]]; then
		log "Sweeping macOS metadata under ${target}"
		"${REPO_ROOT}/scripts/cleanup-macos-cruft.sh" "${target}" >/dev/null
	fi
}

cleanup_target "${REPO_ROOT}/dist"
cleanup_target "${REPO_ROOT}/vendor"
cleanup_target "${REPO_ROOT}/.venv"

if poetry_env_path=$(poetry env info --path 2>/dev/null); then
	cleanup_target "${poetry_env_path}"
fi

: "${ALLOW_CHECK_CRUFT_CLEANUP:=true}"
: "${AUTO_CLEAN_CRUFT:=auto}"

export ALLOW_CHECK_CRUFT_CLEANUP
export AUTO_CLEAN_CRUFT

log "Running manage-deps.sh $*"
"${REPO_ROOT}/scripts/manage-deps.sh" "$@"
