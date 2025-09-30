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
UPDATE_ALL="false"
UPDATE_PACKAGES=()
ALLOW_SDIST_OVERRIDES="argon2-cffi-bindings"
CHECK_ONLY="false"

WHEELHOUSE_ROOT="${REPO_ROOT}/dist/wheelhouse"
REQUIREMENTS_ROOT="${REPO_ROOT}/dist/requirements"

log() {
	printf '[deps] %s\n' "$*"
}

usage() {
	sed -n '1,40p' "$0"
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

pushd "${REPO_ROOT}" >/dev/null

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

if [[ ${RUN_EXPORT} == "true" ]]; then
	if [[ ${CHECK_ONLY} == "true" ]]; then
		log "Dry-run: validating export commands"
		poetry export --without-hashes >/dev/null
		if [[ -n ${EXTRAS} ]]; then
			poetry export --without-hashes --extras "${EXTRAS}" >/dev/null
		fi
		if [[ ${INCLUDE_DEV} == "true" ]]; then
			poetry export --without-hashes --with dev >/dev/null
		fi
	else
		mkdir -p "${REQUIREMENTS_ROOT}"

		log "Exporting base requirements"
		poetry export --without-hashes -o "${REQUIREMENTS_ROOT}/base.txt"

		if [[ -n ${EXTRAS} ]]; then
			log "Exporting requirements with extras: ${EXTRAS}"
			poetry export --without-hashes --extras "${EXTRAS}" \
				-o "${REQUIREMENTS_ROOT}/extras.txt"
		fi

		if [[ ${INCLUDE_DEV} == "true" ]]; then
			log "Exporting dev requirements"
			poetry export --without-hashes --with dev \
				-o "${REQUIREMENTS_ROOT}/dev.txt"
		fi
	fi
else
	log "Skipping requirements export"
fi

if [[ ${RUN_WHEELHOUSE} == "true" ]]; then
	if [[ ${CHECK_ONLY} == "true" ]]; then
		log "Dry-run: skipping wheelhouse build (validation only)"
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
