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
#   GENERATE_SUPPLY_CHAIN When "true", generate SBOM, run OSV scan, create bundle (default: false)
#   CREATE_BUNDLE    When "true", create portable wheelhouse bundle with checksums (default: false)
#   COMMIT_SHA       Git commit SHA for bundle metadata
#   GIT_REF          Git reference (branch/tag) for bundle metadata
#
# The resulting directory will contain a requirements.txt file and cached
# wheels. Copy the directory (or archive) alongside the repository and install
# with:
#   python -m pip install --no-index --find-links <wheelhouse> -r requirements.txt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WHEELHOUSE="${1:-${REPO_ROOT}/vendor/wheelhouse}"
REQ_FILE="${WHEELHOUSE}/requirements.txt"
PRIMARY_REQ_FILE=""
SDIST_REQ_FILE=""
DOWNLOAD_REQ_FILE="${REQ_FILE}"
EXTRAS_LIST="${EXTRAS-}"
INCLUDE_DEV="${INCLUDE_DEV:-false}"
CREATE_ARCHIVE="${CREATE_ARCHIVE:-false}"
PLATFORM="${PLATFORM-}"
PARALLEL_DOWNLOADS="${PARALLEL_DOWNLOADS:-4}"
RETRY_COUNT="${RETRY_COUNT:-3}"
PREFER_BINARY="${PREFER_BINARY:-true}"
TARGET_PYTHON_VERSION="${TARGET_PYTHON_VERSION-}"
ALLOW_SDIST_FOR="${ALLOW_SDIST_FOR-}"
PYTHON_CANDIDATES=("python3" "python")
PIP_LOG="${WHEELHOUSE}/pip-download.log"
REMEDIATION_DIR="${WHEELHOUSE}/remediation"
REMEDIATION_SUMMARY="${REMEDIATION_DIR}/wheelhouse-remediation.json"

# Detect platform if not specified
if [[ -z ${PLATFORM} ]]; then
	case "$(uname -s)" in
	Linux*)
		ARCH="$(uname -m)"
		case "${ARCH}" in
		x86_64) PLATFORM="manylinux2014_x86_64" ;;
		aarch64 | arm64) PLATFORM="manylinux2014_aarch64" ;;
		ppc64le) PLATFORM="manylinux2014_ppc64le" ;;
		s390x) PLATFORM="manylinux2014_s390x" ;;
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
	MINGW* | CYGWIN* | MSYS*)
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

if [[ -n ${PYTHON_BIN-} ]]; then
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

if [[ -n ${POETRY-} ]]; then
	read -r -a POETRY_CMD <<<"${POETRY}"
else
	if command -v poetry >/dev/null 2>&1; then
		POETRY_CMD=("poetry")
	else
		POETRY_CMD=("${PYTHON_CMD[@]}" "-m" "poetry")
	fi
fi

if [[ ${#POETRY_CMD[@]} -eq 0 ]]; then
	printf >&2 'Unable to locate Poetry executable. Set POETRY or ensure poetry is on PATH.\n'
	exit 1
fi

POETRY_DESC="${POETRY_CMD[*]}"

to_lower() {
	printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

generate_remediation_summary() {
	local log_path="$1"
	local summary_path="$2"
	local python_version="$3"

	if [[ ! -f ${log_path} ]]; then
		return
	fi

	mkdir -p "$(dirname "${summary_path}")"

	local cmd=("${PYTHON_CMD[@]}" "-m" "prometheus.remediation" "wheelhouse" "--log" "${log_path}" "--output" "${summary_path}" "--platform" "${PLATFORM}")
	if [[ -n ${python_version} ]]; then
		cmd+=("--python-version" "${python_version}")
	fi
	if ! "${cmd[@]}"; then
		printf 'Warning: Failed to produce remediation summary\n' >&2
	else
		printf 'Remediation summary written to %s\n' "${summary_path}"
	fi
}

# Create platform-specific wheelhouse structure
PLATFORM_WHEELHOUSE="${WHEELHOUSE}/platform/${PLATFORM}"
ARCHIVE_PATH="${WHEELHOUSE}.tar.gz"

# Start fresh to avoid stale files from previous runs.
rm -rf "${WHEELHOUSE}"
mkdir -p "${WHEELHOUSE}" "${PLATFORM_WHEELHOUSE}"
rm -f "${PIP_LOG}"

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

printf 'Exporting dependency graph with poetry (%s)\n' "${POETRY_DESC}"

# Check if poetry export is available (requires poetry-plugin-export)
if ! "${POETRY_CMD[@]}" export --help >/dev/null 2>&1; then
	printf 'Warning: poetry export not available. Installing poetry-plugin-export...\n'
	"${PYTHON_CMD[@]}" -m pip install --quiet poetry-plugin-export || {
		printf >&2 'Failed to install poetry-plugin-export. Using alternative method.\n'
		# Alternative: generate requirements from lock file using Python
		"${PYTHON_CMD[@]}" - <<PY
import sys
import tomllib
from pathlib import Path
import os

lock_file = Path("poetry.lock")
if not lock_file.exists():
    print("Error: poetry.lock not found", file=sys.stderr)
    sys.exit(1)

with open(lock_file, "rb") as f:
    lock_data = tomllib.load(f)

requirements = []
for package in lock_data.get("package", []):
    name = package.get("name", "")
    version = package.get("version", "")
    if name and version:
        requirements.append(f"{name}=={version}")

wheelhouse_dir = Path("${WHEELHOUSE}")
wheelhouse_dir.mkdir(parents=True, exist_ok=True)
req_file = wheelhouse_dir / "requirements.txt"
req_file.write_text("\\n".join(sorted(requirements)) + "\\n")
print(f"Generated {len(requirements)} requirements to {req_file}")
PY
		REQ_FILE="${WHEELHOUSE}/requirements.txt"
		if [[ ! -f ${REQ_FILE} ]]; then
			printf >&2 'Failed to generate requirements file\n'
			exit 1
		fi
	}
fi

# Export requirements if poetry export is available
if "${POETRY_CMD[@]}" export --help >/dev/null 2>&1; then
	"${POETRY_CMD[@]}" export "${EXPORT_ARGS[@]}" -o "${REQ_FILE}"
fi

ALLOW_SDIST_PACKAGES=()
SDIST_PACKAGES_FILE=""
if [[ -n ${ALLOW_SDIST_FOR} ]]; then
	IFS=',' read -ra __allow_sdist_split <<<"${ALLOW_SDIST_FOR}"
	for pkg in "${__allow_sdist_split[@]}"; do
		pkg_trimmed="${pkg// /}"
		if [[ -n ${pkg_trimmed} ]]; then
			ALLOW_SDIST_PACKAGES+=("$(to_lower "${pkg_trimmed}")")
		fi
	done
	unset __allow_sdist_split
fi

if [[ ${#ALLOW_SDIST_PACKAGES[@]} -gt 0 && -f ${REQ_FILE} ]]; then
	PRIMARY_REQ_FILE="${WHEELHOUSE}/requirements-primary.txt"
	SDIST_REQ_FILE="${WHEELHOUSE}/requirements-sdist.txt"
	SDIST_PACKAGES_FILE="${WHEELHOUSE}/requirements-sdist-packages.txt"
	ALLOW_SDIST_TARGETS="$(
		IFS=','
		printf '%s' "${ALLOW_SDIST_PACKAGES[*]}"
	)"

	ALLOW_SDIST_TARGETS="${ALLOW_SDIST_TARGETS}" \
		ORIG_REQ_FILE="${REQ_FILE}" \
		PRIMARY_REQ_FILE="${PRIMARY_REQ_FILE}" \
		SDIST_REQ_FILE="${SDIST_REQ_FILE}" \
		SDIST_PACKAGES_FILE="${SDIST_PACKAGES_FILE}" \
		"${PYTHON_CMD[@]}" - <<'PY'
import os
from pathlib import Path

try:
	from packaging.requirements import Requirement  # type: ignore
except Exception:  # pragma: no cover - packaging ships with pip
	Requirement = None

try:
	from packaging.utils import canonicalize_name  # type: ignore
except Exception:  # pragma: no cover - packaging ships with pip
	def canonicalize_name(value: str) -> str:  # type: ignore
		value = value.strip().lower()
		return value.replace("_", "-")

allow = {
	canonicalize_name(name.strip())
	for name in os.environ.get("ALLOW_SDIST_TARGETS", "").split(",")
	if name.strip()
}

orig = Path(os.environ["ORIG_REQ_FILE"])
primary_path = Path(os.environ["PRIMARY_REQ_FILE"])
sdist_path = Path(os.environ["SDIST_REQ_FILE"])
sdist_packages_path = Path(os.environ["SDIST_PACKAGES_FILE"])

primary_lines = []
sdist_lines = []
sdist_names = []

def extract_name(entry: str) -> str:
	entry = entry.strip()
	if not entry or entry.startswith("#"):
		return ""
	if Requirement is not None:
		try:
			return canonicalize_name(Requirement(entry).name)
		except Exception:  # pragma: no cover - fall back to manual parse
			pass
	fragment = entry.split(";", 1)[0].strip()
	for separator in ("[", "@", "==", "!=", ">=", "<=", "~=", "==="):
		if separator in fragment:
			fragment = fragment.split(separator, 1)[0]
	return canonicalize_name(fragment)

for line in orig.read_text().splitlines():
	name = extract_name(line)
	if not name:
		primary_lines.append(line)
		continue
	if name in allow:
		sdist_lines.append(line)
		sdist_names.append(name)
	else:
		primary_lines.append(line)

if primary_lines:
	primary_path.write_text("\n".join(primary_lines) + "\n")
else:
	primary_path.unlink(missing_ok=True)  # type: ignore[call-arg]

if sdist_lines:
	sdist_path.write_text("\n".join(sdist_lines) + "\n")
else:
	sdist_path.unlink(missing_ok=True)  # type: ignore[call-arg]

if sdist_names:
	sdist_names_sorted = sorted(set(sdist_names))
	sdist_packages_path.write_text("\n".join(sdist_names_sorted) + "\n")
else:
	sdist_packages_path.unlink(missing_ok=True)  # type: ignore[call-arg]

print(f"Primary requirements: {len(primary_lines)}")
print(f"Allowlisted requirements: {len(sdist_lines)}")
PY

	if [[ -f ${PRIMARY_REQ_FILE} ]]; then
		if [[ -s ${PRIMARY_REQ_FILE} ]]; then
			DOWNLOAD_REQ_FILE="${PRIMARY_REQ_FILE}"
			printf 'Using primary requirements file %s (allowlist split)\n' "${DOWNLOAD_REQ_FILE}"
		else
			rm -f "${PRIMARY_REQ_FILE}"
			PRIMARY_REQ_FILE=""
		fi
	fi

	if [[ -f ${SDIST_REQ_FILE} ]]; then
		if [[ ! -s ${SDIST_REQ_FILE} ]]; then
			rm -f "${SDIST_REQ_FILE}"
			SDIST_REQ_FILE=""
		else
			printf 'Allowlisted requirements written to %s\n' "${SDIST_REQ_FILE}"
		fi
	fi

	if [[ -n ${SDIST_PACKAGES_FILE} && -f ${SDIST_PACKAGES_FILE} && ! -s ${SDIST_PACKAGES_FILE} ]]; then
		rm -f "${SDIST_PACKAGES_FILE}"
	fi
fi

printf 'Resolved download requirements file: %s\n' "${DOWNLOAD_REQ_FILE}"

# Build pip download arguments for optimal performance
PIP_DOWNLOAD_ARGS=(
	"--dest" "${WHEELHOUSE}"
	"--requirement" "${DOWNLOAD_REQ_FILE}"
	"--progress-bar" "on"
	"--log" "${PIP_LOG}"
)

PYTHON_VERSION_FOR_PIP_ARG=""
PYTHON_VERSION_FOR_ABI=""

# Add platform-specific arguments
if [[ ${PLATFORM} != "any" ]]; then
	PIP_DOWNLOAD_ARGS+=("--platform" "${PLATFORM}")

	if [[ -n ${TARGET_PYTHON_VERSION} ]]; then
		PYTHON_VERSION_FOR_PIP_ARG="${TARGET_PYTHON_VERSION}"
		PYTHON_VERSION_FOR_ABI="${TARGET_PYTHON_VERSION//./}"
	else
		__version_output="$(
			"${PYTHON_CMD[@]}" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
print(f"{sys.version_info.major}{sys.version_info.minor}")
PY
		)"
		IFS=$'\n' read -r PYTHON_VERSION_FOR_PIP_ARG PYTHON_VERSION_FOR_ABI <<<"${__version_output}"
		unset __version_output
	fi

	# pip requires explicit interpreter constraints when --platform is used
	if [[ -n ${PYTHON_VERSION_FOR_PIP_ARG} ]]; then
		PIP_DOWNLOAD_ARGS+=("--python-version" "${PYTHON_VERSION_FOR_PIP_ARG}")
	fi

	IMPLEMENTATION_TAG=$(
		"${PYTHON_CMD[@]}" - <<'PY'
import platform
impl = platform.python_implementation()
print('cp' if impl == 'CPython' else impl.lower())
PY
	)

	if [[ -n ${IMPLEMENTATION_TAG} ]]; then
		PIP_DOWNLOAD_ARGS+=("--implementation" "${IMPLEMENTATION_TAG}")
	fi

	if [[ -n ${TARGET_PYTHON_VERSION} && ${IMPLEMENTATION_TAG} == "cp" ]]; then
		if [[ -n ${PYTHON_VERSION_FOR_ABI} ]]; then
			ABI_TAG="cp${PYTHON_VERSION_FOR_ABI}"
		else
			ABI_TAG="cp${TARGET_PYTHON_VERSION//./}"
		fi
	else
		ABI_TAG=$(
			"${PYTHON_CMD[@]}" - <<'PY'
try:
    from packaging import tags
except ImportError:  # pragma: no cover - packaging is a transitive dependency of pip
    import sys
    sys.exit(0)

tag = next(tags.sys_tags(), None)
print(tag.abi if tag else '')
PY
		)
	fi

	if [[ -n ${ABI_TAG} ]]; then
		PIP_DOWNLOAD_ARGS+=("--abi" "${ABI_TAG}")
	fi

	# pip 25+ requires --only-binary when platform restrictions are used
	PIP_DOWNLOAD_ARGS+=("--only-binary=:all:")
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
	: >"${PIP_LOG}"
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
			remediation_python_version="${TARGET_PYTHON_VERSION:-${PYTHON_VERSION_FOR_PIP_ARG}}"
			generate_remediation_summary "${PIP_LOG}" "${REMEDIATION_SUMMARY}" "${remediation_python_version}"
			exit ${exit_code}
		fi
	fi
done

if [[ -n ${SDIST_REQ_FILE} ]]; then
	printf 'Downloading fallback sdists for allowlisted packages (%s)\n' "${SDIST_REQ_FILE}"
	SDIST_DOWNLOAD_ARGS=(
		"--dest" "${WHEELHOUSE}"
		"--requirement" "${SDIST_REQ_FILE}"
		"--no-deps"
		"--progress-bar" "on"
		"--retries" "${RETRY_COUNT}"
		"--timeout" "300"
	)

	if [[ $(to_lower "${PREFER_BINARY}") == "true" ]]; then
		SDIST_DOWNLOAD_ARGS+=("--prefer-binary")
	fi

	if ! "${PYTHON_CMD[@]}" -m pip download "${SDIST_DOWNLOAD_ARGS[@]}"; then
		printf >&2 'Failed to download allowlisted packages that require sdists\n'
		exit 1
	fi
fi

SDIST_USED_PACKAGES=()
if [[ -n ${SDIST_PACKAGES_FILE} && -f ${SDIST_PACKAGES_FILE} ]]; then
	while IFS= read -r pkg_name; do
		pkg_trimmed="${pkg_name// /}"
		[[ -n ${pkg_trimmed} ]] && SDIST_USED_PACKAGES+=("${pkg_trimmed}")
	done <"${SDIST_PACKAGES_FILE}"
	if [[ ${#SDIST_USED_PACKAGES[@]} -gt 0 ]]; then
		SDIST_USED_DISPLAY="$(
			IFS=','
			printf '%s' "${SDIST_USED_PACKAGES[*]}"
		)"
		printf '::warning::Allowlisted packages downloaded via sdist: %s\n' \
			"${SDIST_USED_DISPLAY}"
	fi
fi

SDIST_USED_JSON="[]"
if [[ ${#SDIST_USED_PACKAGES[@]} -gt 0 ]]; then
	SDIST_USED_JSON="[$(printf '"%s",' "${SDIST_USED_PACKAGES[@]}" | sed 's/,$//')]"
fi

# Organize wheels by platform
if [[ -d ${PLATFORM_WHEELHOUSE} ]]; then
	printf 'Organizing platform-specific wheels\n'
	find "${WHEELHOUSE}" -maxdepth 1 -name "*.whl" -exec mv {} "${PLATFORM_WHEELHOUSE}/" \; 2>/dev/null || true
fi

# Create a platform manifest
cat >"${WHEELHOUSE}/platform_manifest.json" <<EOF
{
    "platform": "${PLATFORM}",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "python_version": "$("${PYTHON_CMD[@]}" --version 2>&1)",
    "extras": "${EXTRAS_LIST}",
    "include_dev": "${INCLUDE_DEV}",
    "allow_sdist_for": [$(printf '"%s",' "${ALLOW_SDIST_PACKAGES[@]}" | sed 's/,$//')],
	"allow_sdist_used": ${SDIST_USED_JSON},
    "wheel_count": $(find "${WHEELHOUSE}" -name "*.whl" | wc -l),
    "total_size": $(du -s "${WHEELHOUSE}" | cut -f1)
}
EOF

if [[ $(to_lower "${CREATE_ARCHIVE}") == "true" ]]; then
	printf 'Creating archive %s\n' "${ARCHIVE_PATH}"
	tar -czf "${ARCHIVE_PATH}" -C "$(dirname "${WHEELHOUSE}")" "$(basename "${WHEELHOUSE}")"
fi

# Enhanced supply chain features (optional)
GENERATE_SUPPLY_CHAIN="${GENERATE_SUPPLY_CHAIN:-false}"
if [[ $(to_lower "${GENERATE_SUPPLY_CHAIN}") == "true" ]]; then
	printf '\n=== Supply Chain Security Features ===\n'
	
	# Generate hash-pinned constraints if uv or pip-tools available
	if command -v uv >/dev/null 2>&1 || command -v pip-compile >/dev/null 2>&1; then
		printf 'Generating hash-pinned constraints...\n'
		CONSTRAINTS_FILE="${WHEELHOUSE}/constraints-hashed.txt"
		"${PYTHON_CMD[@]}" - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("${REPO_ROOT}").resolve()))
from chiron.deps.constraints import generate_constraints

success = generate_constraints(
    project_root=Path("${REPO_ROOT}"),
    output_path=Path("${CONSTRAINTS_FILE}"),
    tool="uv" if shutil.which("uv") else "pip-tools",
    include_extras="${EXTRAS_LIST}".split(",") if "${EXTRAS_LIST}" else None,
)
sys.exit(0 if success else 1)
PY
		if [[ $? -eq 0 ]]; then
			printf '✓ Generated hash-pinned constraints: %s\n' "${CONSTRAINTS_FILE}"
		else
			printf '⚠ Failed to generate constraints\n' >&2
		fi
	fi
	
	# Generate SBOM if cyclonedx-py available
	if command -v cyclonedx-py >/dev/null 2>&1; then
		printf 'Generating SBOM...\n'
		SBOM_FILE="${WHEELHOUSE}/sbom.json"
		cyclonedx-py --format json -o "${SBOM_FILE}" "${REPO_ROOT}" 2>/dev/null
		if [[ -f ${SBOM_FILE} ]]; then
			printf '✓ Generated SBOM: %s\n' "${SBOM_FILE}"
		else
			printf '⚠ Failed to generate SBOM\n' >&2
		fi
	fi
	
	# Run OSV scan if osv-scanner available
	if command -v osv-scanner >/dev/null 2>&1 && [[ -f ${REQ_FILE} ]]; then
		printf 'Running vulnerability scan...\n'
		OSV_FILE="${WHEELHOUSE}/osv.json"
		osv-scanner --lockfile="${REQ_FILE}" --format=json > "${OSV_FILE}" 2>/dev/null || true
		if [[ -f ${OSV_FILE} ]]; then
			printf '✓ Saved vulnerability scan: %s\n' "${OSV_FILE}"
		else
			printf '⚠ Failed to run vulnerability scan\n' >&2
		fi
	fi
	
	# Generate wheelhouse bundle with checksums
	if [[ $(to_lower "${CREATE_BUNDLE}") == "true" ]]; then
		printf 'Creating portable wheelhouse bundle...\n'
		BUNDLE_FILE="${WHEELHOUSE}.tar.gz"
		"${PYTHON_CMD[@]}" - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("${REPO_ROOT}").resolve()))
from chiron.deps.bundler import create_wheelhouse_bundle

metadata = create_wheelhouse_bundle(
    wheelhouse_dir=Path("${WHEELHOUSE}"),
    output_path=Path("${BUNDLE_FILE}"),
    commit_sha="${COMMIT_SHA:-}",
    git_ref="${GIT_REF:-}",
)
print(f"Bundle created: {metadata.wheel_count} wheels, {metadata.total_size_bytes} bytes")
PY
		if [[ $? -eq 0 ]]; then
			printf '✓ Created bundle: %s\n' "${BUNDLE_FILE}"
			
			# Sign bundle if cosign available
			if command -v cosign >/dev/null 2>&1; then
				printf 'Signing bundle...\n'
				export COSIGN_EXPERIMENTAL=1
				cosign sign-blob --yes "${BUNDLE_FILE}" > "${BUNDLE_FILE}.sig" 2>/dev/null
				if [[ $? -eq 0 ]]; then
					printf '✓ Signed bundle: %s.sig\n' "${BUNDLE_FILE}"
				else
					printf '⚠ Failed to sign bundle\n' >&2
				fi
			fi
		else
			printf '⚠ Failed to create bundle\n' >&2
		fi
	fi
fi

printf 'Wheelhouse ready: %s\n' "${WHEELHOUSE}"
printf 'Platform: %s\n' "${PLATFORM}"
printf 'Wheel count: %s\n' "$(find "${WHEELHOUSE}" -name "*.whl" | wc -l)"
if [[ $(to_lower "${CREATE_ARCHIVE}") == "true" ]]; then
	printf 'Archive created at: %s\n' "${ARCHIVE_PATH}"
fi
