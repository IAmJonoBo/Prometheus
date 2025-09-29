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
#   PLATFORM         Target platform for wheels (e.g. "linux_x86_64", "macosx_11_0_arm64")
#   PARALLEL_DOWNLOADS Maximum parallel downloads (default: 4)
#   RETRY_COUNT      Number of retry attempts for failed downloads (default: 3)
#   PREFER_BINARY    When "true", prefer binary wheels over source distributions
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
PLATFORM="${PLATFORM-}"
PARALLEL_DOWNLOADS="${PARALLEL_DOWNLOADS:-4}"
RETRY_COUNT="${RETRY_COUNT:-3}"
PREFER_BINARY="${PREFER_BINARY:-true}"
PYTHON_CANDIDATES=("python3" "python")

# Detect platform if not specified
if [[ -z ${PLATFORM} ]]; then
    case "$(uname -s)" in
        Linux*)     
            ARCH="$(uname -m)"
            case "${ARCH}" in
                x86_64) PLATFORM="linux_x86_64" ;;
                aarch64|arm64) PLATFORM="linux_aarch64" ;;
                *) PLATFORM="linux_${ARCH}" ;;
            esac
            ;;
        Darwin*)    
            ARCH="$(uname -m)"
            MACOS_VERSION="$(sw_vers -productVersion | cut -d. -f1-2 | tr . _)"
            case "${ARCH}" in
                x86_64) PLATFORM="macosx_${MACOS_VERSION}_x86_64" ;;
                arm64) PLATFORM="macosx_${MACOS_VERSION}_arm64" ;;
                *) PLATFORM="macosx_${MACOS_VERSION}_${ARCH}" ;;
            esac
            ;;
        MINGW*|CYGWIN*|MSYS*)
            ARCH="$(uname -m)"
            case "${ARCH}" in
                x86_64) PLATFORM="win_amd64" ;;
                i686) PLATFORM="win32" ;;
                *) PLATFORM="win_${ARCH}" ;;
            esac
            ;;
        *) 
            printf >&2 'Warning: Unknown platform, using generic platform tag\n'
            PLATFORM="any"
            ;;
    esac
fi

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

# Create platform-specific wheelhouse structure
PLATFORM_WHEELHOUSE="${WHEELHOUSE}/platform/${PLATFORM}"
ARCHIVE_PATH="${WHEELHOUSE}.tar.gz"

# Start fresh to avoid stale files from previous runs.
rm -rf "${WHEELHOUSE}"
mkdir -p "${WHEELHOUSE}" "${PLATFORM_WHEELHOUSE}"

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

# Build pip download arguments for optimal performance
PIP_DOWNLOAD_ARGS=(
    "--dest" "${WHEELHOUSE}"
    "--requirement" "${REQ_FILE}"
    "--progress-bar" "on"
)

# Add platform-specific arguments
if [[ ${PLATFORM} != "any" ]]; then
    PIP_DOWNLOAD_ARGS+=("--platform" "${PLATFORM}")
fi

# Add binary preference
if [[ $(to_lower "${PREFER_BINARY}") == "true" ]]; then
    PIP_DOWNLOAD_ARGS+=("--prefer-binary")
fi

# Add retry and timeout settings
PIP_DOWNLOAD_ARGS+=(
    "--retries" "${RETRY_COUNT}"
    "--timeout" "300"
)

printf 'Downloading wheels into %s (platform: %s)\n' "${WHEELHOUSE}" "${PLATFORM}"

# Attempt download with retries
download_attempt=1
while [[ ${download_attempt} -le ${RETRY_COUNT} ]]; do
    if "${PYTHON_CMD[@]}" -m pip download "${PIP_DOWNLOAD_ARGS[@]}"; then
        printf 'Download completed successfully\n'
        break
    else
        exit_code=$?
        if [[ ${download_attempt} -lt ${RETRY_COUNT} ]]; then
            printf 'Download attempt %d failed, retrying in 5 seconds...\n' "${download_attempt}"
            sleep 5
            download_attempt=$((download_attempt + 1))
        else
            printf >&2 'All download attempts failed\n'
            exit ${exit_code}
        fi
    fi
done

# Organize wheels by platform
if [[ -d ${PLATFORM_WHEELHOUSE} ]]; then
    printf 'Organizing platform-specific wheels\n'
    find "${WHEELHOUSE}" -maxdepth 1 -name "*.whl" -exec mv {} "${PLATFORM_WHEELHOUSE}/" \; 2>/dev/null || true
fi

# Create a platform manifest
cat > "${WHEELHOUSE}/platform_manifest.json" <<EOF
{
    "platform": "${PLATFORM}",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "python_version": "$("${PYTHON_CMD[@]}" --version 2>&1)",
    "extras": "${EXTRAS_LIST}",
    "include_dev": "${INCLUDE_DEV}",
    "wheel_count": $(find "${WHEELHOUSE}" -name "*.whl" | wc -l),
    "total_size": $(du -s "${WHEELHOUSE}" | cut -f1)
}
EOF

if [[ $(to_lower "${CREATE_ARCHIVE}") == "true" ]]; then
	printf 'Creating archive %s\n' "${ARCHIVE_PATH}"
	tar -czf "${ARCHIVE_PATH}" -C "$(dirname "${WHEELHOUSE}")" "$(basename "${WHEELHOUSE}")"
fi

printf 'Wheelhouse ready: %s\n' "${WHEELHOUSE}"
printf 'Platform: %s\n' "${PLATFORM}"
printf 'Wheel count: %s\n' "$(find "${WHEELHOUSE}" -name "*.whl" | wc -l)"
if [[ $(to_lower "${CREATE_ARCHIVE}") == "true" ]]; then
	printf 'Archive created at: %s\n' "${ARCHIVE_PATH}"
fi
