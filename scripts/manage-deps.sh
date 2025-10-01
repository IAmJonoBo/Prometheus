#!/usr/bin/env bash
#
# manage-deps.sh - Orchestrate dependency refresh, exports, and wheel builds.
#
# This helper keeps Poetry metadata, exported requirements, and the offline
# wheelhouse in sync. It can be used locally, in CI, or as a Renovate post-update
# hook so dependency upgrades automatically regenerate all derived artifacts.
#
# Usage (most common):
#   scripts/manage-deps.sh
#
# Flags:
#   --python-versions "3.11 3.12"  Space-separated Python versions to target
#   --platforms "manylinux2014_x86_64"  Platform tags to build wheels for
#   --extras "pii,observability,..."  Extras list to include in exports/wheels
#   --include-dev / --no-include-dev  Toggle dev dependency exports (default on)
#   --skip-lock         Skip running `poetry lock`
#   --skip-export       Skip generating requirements exports
#   --skip-wheelhouse   Skip wheelhouse builds
#   --update-all        Run `poetry update`
#   --update "pkg1 pkg2"  Update only the selected packages
#   --allow-sdist "pkg"  Comma list of packages allowed to fall back to sdists
#   --check             Do a dry run (no writes) but execute validation steps
#   -h | --help         Display this message
#
# Environment:
#   AUTO_CLEAN_CRUFT           Controls macOS metadata cleanup (auto/true/false)
#   ALLOW_CHECK_CRUFT_CLEANUP  When true, remove macOS metadata even in --check mode
#
# The script writes exports to dist/requirements/ and wheel artifacts to
# dist/wheelhouse/<platform>/py<version>/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_VERSIONS=("3.11" "3.12")
PLATFORMS=("manylinux2014_x86_64")
EXTRAS="pii,observability,rag,llm,governance,integrations"
INCLUDE_DEV="true"
RUN_LOCK="true"
RUN_EXPORT="true"
RUN_WHEELHOUSE="true"
RUN_PREFLIGHT="true"
UPDATE_ALL="false"
UPDATE_PACKAGES=()
ALLOW_SDIST_OVERRIDES="numpy,rapidfuzz,llama-cpp-python,pywin32,pywinpty"
CHECK_ONLY="false"
AUTO_CLEAN_CRUFT="${AUTO_CLEAN_CRUFT:-auto}"
ALLOW_CHECK_CRUFT_CLEANUP="${ALLOW_CHECK_CRUFT_CLEANUP:-false}"

POETRY_EXTRAS_ARGS=()

WHEELHOUSE_ROOT="${REPO_ROOT}/dist/wheelhouse"
REQUIREMENTS_ROOT="${REPO_ROOT}/dist/requirements"
CONSTRAINTS_ROOT="${REPO_ROOT}/constraints"

to_lower() {
	printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

should_clean_cruft() {
	local setting
	setting="$(to_lower "${AUTO_CLEAN_CRUFT}")"
	case "${setting}" in
	true | 1 | yes)
		return 0
		;;
	false | 0 | no)
		return 1
		;;
	auto | "")
		[[ $(uname -s) == "Darwin" ]]
		return $?
		;;
	*)
		[[ $(uname -s) == "Darwin" ]]
		return $?
		;;
	esac
}

cleanup_cruft_in_path() {
	local target="$1"
	[[ -d ${target} ]] || return
	local -a find_args=(
		"${target}"
		"(" -name "._*" -o -name ".DS_Store" -o -name ".AppleDouble" -o -name "Icon?" -o -name "__MACOSX" ")"
		-print0
	)
	local -a entries=()
	while IFS= read -r -d '' entry; do
		entries+=("${entry}")
	done < <(find "${find_args[@]}")
	local count=${#entries[@]}
	if [[ ${count} -eq 0 ]]; then
		return
	fi
	local allow_check_clean="false"
	if [[ ${CHECK_ONLY} == "true" ]]; then
		case "$(to_lower "${ALLOW_CHECK_CRUFT_CLEANUP}")" in
		true | 1 | yes)
			allow_check_clean="true"
			;;
		*)
			allow_check_clean="false"
			;;
		esac
	fi
	if [[ ${CHECK_ONLY} == "true" && ${allow_check_clean} != "true" ]]; then
		log "Detected ${count} macOS metadata artefacts under ${target}"
		CRUFT_DETECTED="true"
		CRUFT_PATHS+=("${target}")
		return
	fi
	if should_clean_cruft; then
		if [[ ${CHECK_ONLY} == "true" ]]; then
			log "Auto-cleaning ${count} macOS metadata artefacts under ${target} (CHECK_ONLY override)"
		else
			log "Removing ${count} macOS metadata artefacts under ${target}"
		fi
		printf '%s\0' "${entries[@]}" | xargs -0 rm -rf
	else
		log "macOS metadata artefacts remain under ${target}; set AUTO_CLEAN_CRUFT=true or run scripts/cleanup-macos-cruft.sh '${target}'"
		CRUFT_DETECTED="true"
		CRUFT_PATHS+=("${target}")
	fi
}

preflight_metadata_cleanup() {
	CRUFT_DETECTED="false"
	CRUFT_PATHS=()

	if ! should_clean_cruft && [[ ${CHECK_ONLY} != "true" ]]; then
		log "Skipping automatic macOS metadata cleanup (AUTO_CLEAN_CRUFT=${AUTO_CLEAN_CRUFT})"
	fi

	local poetry_env=""
	if poetry_env=$(poetry env info --path 2>/dev/null); then
		cleanup_cruft_in_path "${poetry_env}"
	fi

	cleanup_cruft_in_path "${REPO_ROOT}/.venv"
	cleanup_cruft_in_path "${REPO_ROOT}/dist"
	cleanup_cruft_in_path "${REPO_ROOT}/vendor"

	if [[ ${CRUFT_DETECTED} == "true" ]]; then
		log "macOS metadata artefacts must be removed before continuing"
		log "Run scripts/cleanup-macos-cruft.sh on the reported paths and retry"
		exit 1
	fi
}

log() {
	printf '[deps] %s\n' "$*"
}

usage() {
	sed -n '1,40p' "$0"
}

detect_python() {
	if command -v python3 >/dev/null 2>&1; then
		PYTHON_CMD=("python3")
		return
	fi
	if command -v python >/dev/null 2>&1; then
		PYTHON_CMD=("python")
		return
	fi
	if command -v py >/dev/null 2>&1; then
		PYTHON_CMD=("py" "-3")
		return
	fi
	log "Unable to locate Python interpreter for extras inspection"
	exit 1
}

filter_defined_extras() {
	if [[ -z ${EXTRAS} ]]; then
		POETRY_EXTRAS_ARGS=()
		return
	fi

	local extras_output
	extras_output="$("${PYTHON_CMD[@]}" -c 'import pathlib
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

data = {}
pyproject = pathlib.Path("pyproject.toml")
if pyproject.exists():
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)

extras = set()
tool = data.get("tool", {})
poetry_cfg = tool.get("poetry", {})
extras.update(poetry_cfg.get("extras", {}).keys())
project = data.get("project", {})
extras.update(project.get("optional-dependencies", {}).keys())
print("\n".join(sorted(extras)))')"

	if [[ -z ${extras_output} ]]; then
		log "No extras defined in pyproject.toml; disabling extras handling"
		EXTRAS=""
		return
	fi

	local -a available_extras=()
	while IFS= read -r extra; do
		[[ -n ${extra} ]] && available_extras+=("${extra}")
	done <<<"${extras_output}"

	local -A extras_map=()
	for extra in "${available_extras[@]}"; do
		[[ -n ${extra} ]] && extras_map["${extra}"]=1
	done

	local -a requested=()
	IFS=',' read -r -a requested <<<"${EXTRAS}"
	local -a filtered=()
	for extra in "${requested[@]}"; do
		local trimmed="${extra// /}"
		[[ -z ${trimmed} ]] && continue
		if [[ -n ${extras_map["${trimmed}"]+x} ]]; then
			filtered+=("${trimmed}")
		else
			log "Skipping undefined extra '${trimmed}'"
		fi
	done

	if [[ ${#filtered[@]} -gt 0 ]]; then
		EXTRAS="$(
			IFS=','
			echo "${filtered[*]}"
		)"
		POETRY_EXTRAS_ARGS=()
		for extra in "${filtered[@]}"; do
			POETRY_EXTRAS_ARGS+=("--extras" "${extra}")
		done
		log "Using extras: ${EXTRAS}"
	else
		log "No requested extras matched pyproject configuration"
		EXTRAS=""
		POETRY_EXTRAS_ARGS=()
	fi
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--python-versions)
		IFS=' ' read -ra PYTHON_VERSIONS <<<"$2"
		shift 2
		;;
	--platforms)
		IFS=' ' read -ra PLATFORMS <<<"$2"
		shift 2
		;;
	--extras)
		EXTRAS="$2"
		shift 2
		;;
	--include-dev)
		INCLUDE_DEV="true"
		shift
		;;
	--no-include-dev)
		INCLUDE_DEV="false"
		shift
		;;
	--skip-lock)
		RUN_LOCK="false"
		shift
		;;
	--skip-export)
		RUN_EXPORT="false"
		shift
		;;
	--skip-wheelhouse)
		RUN_WHEELHOUSE="false"
		shift
		;;
	--update-all)
		UPDATE_ALL="true"
		shift
		;;
	--update)
		IFS=' ' read -ra UPDATE_PACKAGES <<<"$2"
		shift 2
		;;
	--allow-sdist)
		ALLOW_SDIST_OVERRIDES="$2"
		shift 2
		;;
	--skip-preflight)
		RUN_PREFLIGHT="false"
		shift
		;;
	--check)
		CHECK_ONLY="true"
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		printf 'Unknown option: %s\n' "$1" >&2
		usage
		exit 1
		;;
	esac
done

PYTHON_CMD=()
detect_python

pushd "${REPO_ROOT}" >/dev/null

preflight_metadata_cleanup

filter_defined_extras

if [[ ${RUN_LOCK} == "true" && ${CHECK_ONLY} != "true" ]]; then
	if [[ ${UPDATE_ALL} == "true" ]]; then
		log "Running poetry update"
		poetry update
	elif [[ ${#UPDATE_PACKAGES[@]} -gt 0 ]]; then
		log "Updating packages: ${UPDATE_PACKAGES[*]}"
		poetry update "${UPDATE_PACKAGES[@]}"
	else
		log "Refreshing lock file (no version bumps)"
		poetry lock
	fi
else
	log "Skipping lock refresh"
fi

log "Running poetry check"
poetry check

if [[ ${RUN_PREFLIGHT} == "true" ]]; then
	PREFLIGHT_CMD=("${PYTHON_CMD[@]}")
	PREFLIGHT_CMD+=("${SCRIPT_DIR}/preflight_deps.py")
	PREFLIGHT_CMD+=("--python-versions" "${PYTHON_VERSIONS[*]}")
	PREFLIGHT_CMD+=("--platforms" "${PLATFORMS[*]}")
	PREFLIGHT_CMD+=("--allow-sdist" "${ALLOW_SDIST_OVERRIDES}")
	PREFLIGHT_CMD+=("--json")
	PREFLIGHT_CMD+=("--quiet")
	PREFLIGHT_CMD+=("--exit-zero")
	if [[ -n ${EXTRAS// /} ]]; then
		PREFLIGHT_CMD+=("--extras" "${EXTRAS}")
	fi
	PREFLIGHT_JSON="$(mktemp)"
	PREFLIGHT_STDERR="$(mktemp)"

	log "Running dependency preflight checks"
	PREFLIGHT_STATUS=0
	if ! "${PREFLIGHT_CMD[@]}" >"${PREFLIGHT_JSON}" 2>"${PREFLIGHT_STDERR}"; then
		PREFLIGHT_STATUS=$?
	fi

	SUMMARY_STATUS=0
	if [[ -s ${PREFLIGHT_JSON} ]]; then
		if ! "${PYTHON_CMD[@]}" "${SCRIPT_DIR}/render_preflight_summary.py" "${PREFLIGHT_JSON}"; then
			SUMMARY_STATUS=1
		fi
	else
		log "Dependency preflight emitted no JSON payload"
	fi

	if [[ -s ${PREFLIGHT_STDERR} ]]; then
		log "Additional preflight errors:"
		sed 's/^/  ! /' "${PREFLIGHT_STDERR}"
		SUMMARY_STATUS=1
	fi

	rm -f "${PREFLIGHT_JSON}" "${PREFLIGHT_STDERR}"

	if [[ ${PREFLIGHT_STATUS} -ne 0 || ${SUMMARY_STATUS} -ne 0 ]]; then
		log "Preflight guardrails failed"
		exit 1
	fi
fi

if [[ ${RUN_EXPORT} == "true" ]]; then
	if [[ ${CHECK_ONLY} == "true" ]]; then
		log "Dry-run: validating export commands"
		poetry export --without-hashes >/dev/null
		if [[ ${#POETRY_EXTRAS_ARGS[@]} -gt 0 ]]; then
			poetry export --without-hashes "${POETRY_EXTRAS_ARGS[@]}" >/dev/null
		fi
		if [[ ${INCLUDE_DEV} == "true" ]]; then
			poetry export --without-hashes --with dev >/dev/null
		fi
		poetry export --without-hashes >/dev/null
	else
		mkdir -p "${REQUIREMENTS_ROOT}"
		mkdir -p "${CONSTRAINTS_ROOT}"

		log "Exporting base requirements"
		poetry export --without-hashes -o "${REQUIREMENTS_ROOT}/base.txt"

		if [[ ${#POETRY_EXTRAS_ARGS[@]} -gt 0 ]]; then
			log "Exporting requirements with extras: ${EXTRAS}"
			poetry export --without-hashes "${POETRY_EXTRAS_ARGS[@]}" \
				-o "${REQUIREMENTS_ROOT}/extras.txt"
		fi

		if [[ ${INCLUDE_DEV} == "true" ]]; then
			log "Exporting dev requirements"
			poetry export --without-hashes --with dev \
				-o "${REQUIREMENTS_ROOT}/dev.txt"
		fi

		log "Exporting pip constraints"
		{
			echo "# Managed by scripts/manage-deps.sh"
			echo "# Generated on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
			poetry export --without-hashes
		} >"${CONSTRAINTS_ROOT}/production.txt"
	fi
else
	log "Skipping requirements export"
fi

if [[ ${RUN_WHEELHOUSE} == "true" ]]; then
	if [[ ${CHECK_ONLY} == "true" ]]; then
		log "Dry-run: wheelhouse build would target the configured matrix"
		extras_display="${EXTRAS:-<none>}"
		allow_sdist_trimmed="${ALLOW_SDIST_OVERRIDES// /}"
		if [[ -z ${allow_sdist_trimmed} ]]; then
			allow_sdist_trimmed="<none>"
		fi
		for platform in "${PLATFORMS[@]}"; do
			for version in "${PYTHON_VERSIONS[@]}"; do
				log "  python=${version} platform=${platform}"
				log "    extras=${extras_display} dev=${INCLUDE_DEV} allow-sdist=${allow_sdist_trimmed}"
			done
		done
	else
		rm -rf "${WHEELHOUSE_ROOT}"
		mkdir -p "${WHEELHOUSE_ROOT}"

		for platform in "${PLATFORMS[@]}"; do
			for version in "${PYTHON_VERSIONS[@]}"; do
				dest="${WHEELHOUSE_ROOT}/${platform}/py${version//./}"
				rm -rf "${dest}"
				mkdir -p "${dest}"

				log "Building wheelhouse for Python ${version} (${platform})"
				ALLOW_SDIST_FOR="${ALLOW_SDIST_OVERRIDES}" \
					TARGET_PYTHON_VERSION="${version}" \
					PLATFORM="${platform}" \
					EXTRAS="${EXTRAS}" \
					INCLUDE_DEV="${INCLUDE_DEV}" \
					CREATE_ARCHIVE="false" \
					bash "${SCRIPT_DIR}/build-wheelhouse.sh" "${dest}"
			done
		done
	fi
else
	log "Skipping wheelhouse build"
fi

log "Dependency management workflow complete"
popd >/dev/null
