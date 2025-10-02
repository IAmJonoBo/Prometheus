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
# dist/wheelhouse/platforms/<platform>/py<version>/ alongside multi-platform
# manifests and archives under dist/wheelhouse/{manifests,archives}/.

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
# Packages temporarily allowed to fall back to sdists when the upstream project
# does not publish manylinux2014 wheels for our target interpreters. Keep this
# list skinny—ideally empty—so the wheelhouse remains fully reproducible.
#
# llama-cpp-python currently ships source-only releases for the CPU build we
# rely on and pytrec-eval-terrier publishes wheels that target newer manylinux
# baselines than our guardrail. Both require a controlled sdist fallback to
# keep offline bootstrap reproducible.
ALLOW_SDIST_OVERRIDES="llama-cpp-python,pytrec-eval-terrier"
CHECK_ONLY="false"
AUTO_CLEAN_CRUFT="${AUTO_CLEAN_CRUFT:-auto}"
ALLOW_CHECK_CRUFT_CLEANUP="${ALLOW_CHECK_CRUFT_CLEANUP:-false}"

POETRY_EXTRAS_ARGS=()

WHEELHOUSE_ROOT="${REPO_ROOT}/dist/wheelhouse"
REQUIREMENTS_ROOT="${REPO_ROOT}/dist/requirements"
CONSTRAINTS_ROOT="${REPO_ROOT}/constraints"
MANIFEST_EXPORT_ROOT="${WHEELHOUSE_ROOT}/manifests"
PLATFORM_MIRROR_ROOT="${WHEELHOUSE_ROOT}/platforms"
ARCHIVE_ROOT="${WHEELHOUSE_ROOT}/archives"
MULTI_MANIFEST_PATH="${WHEELHOUSE_ROOT}/multi_platform_manifest.json"
PRIMARY_REQUIREMENTS_PATH="${WHEELHOUSE_ROOT}/requirements.txt"

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

log "Ensuring python tooling dependencies are available"
if ! "${PYTHON_CMD[@]}" -m pip --version >/dev/null 2>&1; then
	log "Bootstrapping pip for ${PYTHON_CMD[*]}"
	if ! "${PYTHON_CMD[@]}" -m ensurepip --upgrade >/dev/null 2>&1; then
		log "Failed to bootstrap pip; install pip for ${PYTHON_CMD[*]} or activate a managed environment"
		exit 1
	fi
fi

if ! "${PYTHON_CMD[@]}" -m pip show packaging >/dev/null 2>&1; then
	log "Installing required 'packaging' module"
	"${PYTHON_CMD[@]}" -m pip install --upgrade packaging
fi

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
	PREFLIGHT_ALLOWLIST_PATH="${REPO_ROOT}/vendor/wheelhouse/allowlisted-sdists.json"
	mkdir -p "$(dirname "${PREFLIGHT_ALLOWLIST_PATH}")"
	PREFLIGHT_CMD+=("--allowlist-summary" "${PREFLIGHT_ALLOWLIST_PATH}")
	if [[ -n ${EXTRAS// /} ]]; then
		PREFLIGHT_CMD+=("--extras" "${EXTRAS}")
	fi
	PREFLIGHT_JSON="$(mktemp)"
	PREFLIGHT_STDERR="$(mktemp)"

	if [[ -z ${PREFLIGHT_ALLOW_NETWORK_FAILURES-} ]]; then
		export PREFLIGHT_ALLOW_NETWORK_FAILURES="warn"
	fi

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
		rm -rf "${MANIFEST_EXPORT_ROOT}" "${PLATFORM_MIRROR_ROOT}" "${ARCHIVE_ROOT}"
		rm -f "${MULTI_MANIFEST_PATH}" "${PRIMARY_REQUIREMENTS_PATH}"
		mkdir -p "${MANIFEST_EXPORT_ROOT}" "${PLATFORM_MIRROR_ROOT}" \
			"${ARCHIVE_ROOT}"
		MANIFEST_RECORDS_FILE="$(mktemp)"
		PRIMARY_REQUIREMENTS_COPIED="false"

		for platform in "${PLATFORMS[@]}"; do
			for version in "${PYTHON_VERSIONS[@]}"; do
				python_tag="py${version//./}"
				dest="${WHEELHOUSE_ROOT}/${platform}/${python_tag}"
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

				if [[ -f ${dest}/requirements.txt && ${PRIMARY_REQUIREMENTS_COPIED} == "false" ]]; then
					cp "${dest}/requirements.txt" "${PRIMARY_REQUIREMENTS_PATH}"
					PRIMARY_REQUIREMENTS_COPIED="true"
				fi

				manifest_path="${dest}/platform_manifest.json"
				if [[ -f ${manifest_path} ]]; then
					printf '%s:::%s:::%s:::%s:::%s\n' \
						"${manifest_path}" "${platform}" "${version}" \
						"${python_tag}" "${dest}" >>"${MANIFEST_RECORDS_FILE}"
				else
					log "Warning: missing platform manifest for Python ${version} (${platform})"
				fi
			done
		done

		if [[ -s ${MANIFEST_RECORDS_FILE} ]]; then
			log "Aggregating wheelhouse metadata"
			if ! WHEELHOUSE_ROOT="${WHEELHOUSE_ROOT}" \
				MANIFEST_RECORDS_FILE="${MANIFEST_RECORDS_FILE}" \
				"${PYTHON_CMD[@]}" - <<'PY'; then
import hashlib
import json
import os
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

wheelhouse_root = Path(os.environ["WHEELHOUSE_ROOT"]).resolve()
records_path = Path(os.environ["MANIFEST_RECORDS_FILE"])
manifest_dir = wheelhouse_root / "manifests"
platform_root = wheelhouse_root / "platforms"
archive_root = wheelhouse_root / "archives"
multi_manifest_path = wheelhouse_root / "multi_platform_manifest.json"

manifest_dir.mkdir(parents=True, exist_ok=True)
platform_root.mkdir(parents=True, exist_ok=True)
archive_root.mkdir(parents=True, exist_ok=True)

records = []
with records_path.open(encoding="utf-8") as handle:
	for raw_line in handle:
		line = raw_line.strip()
		if not line:
			continue
		parts = line.split(":::", 4)
		if len(parts) != 5:
			continue
		manifest_str, platform_tag, py_version, py_tag, dest_str = parts
		records.append(
			(
				Path(manifest_str),
				platform_tag,
				py_version,
				py_tag,
				Path(dest_str),
			)
		)

if not records:
	sys.exit(0)


def sha256sum(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as file_handle:
		for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


multi_entries = []
platform_set = set()
python_versions = set()
extras_set = set()
allow_sdist_for = set()
allow_sdist_used = set()
total_wheels = 0

for manifest_path, platform_tag, py_version, py_tag, dest in records:
	if not manifest_path.exists() or not dest.exists():
		continue
	data = json.loads(manifest_path.read_text(encoding="utf-8"))
	data["platform_tag"] = platform_tag
	data["python_target"] = py_version
	try:
		data["relative_path"] = str(dest.relative_to(wheelhouse_root))
	except ValueError:
		data["relative_path"] = str(dest)
	data.setdefault("allow_sdist_for", data.get("allow_sdist_for", []))
	data.setdefault("allow_sdist_used", data.get("allow_sdist_used", []))

	total_wheels += int(data.get("wheel_count", 0))
	if platform_tag:
		platform_set.add(platform_tag)
	if py_version:
		python_versions.add(py_version)
	extras = data.get("extras")
	if extras:
		for item in extras.split(","):
			item = item.strip()
			if item:
				extras_set.add(item)
	for package in data.get("allow_sdist_for") or []:
		if package:
			allow_sdist_for.add(package)
	for package in data.get("allow_sdist_used") or []:
		if package:
			allow_sdist_used.add(package)

	manifest_export = manifest_dir / f"{platform_tag}-{py_tag}.json"
	manifest_export.write_text(
		json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
	)

	target_dir = platform_root / platform_tag / py_tag
	if target_dir.exists():
		shutil.rmtree(target_dir)
	shutil.copytree(dest, target_dir)

	dst_manifest = target_dir / "manifest.json"
	dst_manifest.write_text(
		json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
	)

	archive_name = f"{platform_tag}-{py_tag}.tar.gz"
	archive_path = archive_root / archive_name
	if archive_path.exists():
		archive_path.unlink()
	with tarfile.open(archive_path, "w:gz") as archive:
		archive.add(dest, arcname=f"{platform_tag}/{py_tag}")
	checksum = sha256sum(archive_path)
	checksum_path = archive_root / f"{archive_name}.sha256"
	checksum_path.write_text(
		f"{checksum}  {archive_name}\n", encoding="utf-8"
	)

	data["archive"] = {
		"path": str(archive_path.relative_to(wheelhouse_root)),
		"sha256": checksum,
		"size": archive_path.stat().st_size,
	}
	multi_entries.append(data)

summary = {
	"generated_at": datetime.now(timezone.utc).isoformat(),
	"platform_count": len(platform_set),
	"python_version_count": len(python_versions),
	"platforms": multi_entries,
	"total_wheels": total_wheels,
	"python_versions": sorted(python_versions),
	"extras_included": sorted(extras_set),
	"allow_sdist_for": sorted(allow_sdist_for),
	"allow_sdist_used": sorted(allow_sdist_used),
}

multi_manifest_path.write_text(
	json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
legacy_manifest_path = wheelhouse_root / "manifest.json"
legacy_manifest_path.write_text(
	json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
				log "Failed to aggregate wheelhouse metadata"
				rm -f "${MANIFEST_RECORDS_FILE}"
				exit 1
			fi
			log "Multi-platform manifest saved to ${MULTI_MANIFEST_PATH}"
		else
			log "No wheelhouse manifests generated; skipping aggregation"
		fi
		rm -f "${MANIFEST_RECORDS_FILE}"
	fi
else
	log "Skipping wheelhouse build"
fi

log "Dependency management workflow complete"
popd >/dev/null
