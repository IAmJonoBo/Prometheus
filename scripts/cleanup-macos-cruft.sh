#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=""
INCLUDE_GIT=false
INCLUDE_POETRY_ENV=false
EXTRA_PATHS=()
SEARCH_ROOTS=()

usage() {
	cat <<'EOF'
Usage: cleanup-macos-cruft.sh [--include-git] [--include-poetry-env] [--extra-path PATH]... [ROOT_DIR]

Removes macOS metadata artefacts (e.g., .DS_Store, AppleDouble) from the
workspace. By default, .git directories are skipped. Pass --include-git to
purge AppleDouble files that may have been copied into the repository metadata
folder (useful after extracting archives with Finder).

Additional options:
  --include-poetry-env   Also scrub the active Poetry virtual environment when
                         detected (falls back gracefully if Poetry is absent)
  --extra-path PATH      Add an additional search root. Can be passed multiple
                         times to cover directories outside the repository.
EOF
}

add_search_root() {
	local candidate="$1"
	if [[ -z ${candidate} ]]; then
		return
	fi
	for existing in "${SEARCH_ROOTS[@]}"; do
		if [[ ${existing} == "${candidate}" ]]; then
			return
		fi
	done
	SEARCH_ROOTS+=("${candidate}")
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--include-git)
		INCLUDE_GIT=true
		shift
		;;
	--include-poetry-env)
		INCLUDE_POETRY_ENV=true
		shift
		;;
	--extra-path)
		if [[ $# -lt 2 ]]; then
			echo "--extra-path requires a PATH argument" >&2
			exit 1
		fi
		EXTRA_PATHS+=("$2")
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	--*)
		echo "Unknown option: $1" >&2
		usage >&2
		exit 1
		;;
	*)
		if [[ -n ${ROOT_DIR} ]]; then
			echo "Multiple root directories provided. Use one ROOT_DIR argument." >&2
			exit 1
		fi
		ROOT_DIR="$1"
		shift
		;;
	esac
done

ROOT_DIR="${ROOT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [[ ! -d ${ROOT_DIR} ]]; then
	echo "Provided root directory does not exist: ${ROOT_DIR}" >&2
	exit 1
fi

shopt -s nullglob dotglob

SEARCH_ROOTS=()
add_search_root "${ROOT_DIR}"

for path in "${EXTRA_PATHS[@]}"; do
	add_search_root "${path}"
done

if [[ ${INCLUDE_POETRY_ENV} == true ]]; then
	if command -v poetry >/dev/null 2>&1; then
		poetry_env_path="$(poetry env info --no-ansi --path 2>/dev/null || true)"
		if [[ -n ${poetry_env_path} && -d ${poetry_env_path} ]]; then
			add_search_root "${poetry_env_path}"
		else
			echo "Poetry virtual environment not found; skipping --include-poetry-env" >&2
		fi
	else
		echo "Poetry command not available; skipping --include-poetry-env" >&2
	fi
fi

PATTERNS=(
	".DS_Store"
	"._*"
	".AppleDouble"
	"Icon?"
	"__MACOSX"
)

for search_root in "${SEARCH_ROOTS[@]}"; do
	if [[ ! -d ${search_root} ]]; then
		echo "Skipping missing search root: ${search_root}" >&2
		continue
	fi

	for pattern in "${PATTERNS[@]}"; do
		if [[ ${INCLUDE_GIT} == true ]]; then
			FIND_EXPR=(-name "${pattern}" -print0)
		else
			FIND_EXPR=(-path "*/.git" -prune -o -name "${pattern}" -print0)
		fi

		while IFS= read -r -d '' path; do
			if [[ -d ${path} ]]; then
				rm -rf "${path}"
			else
				rm -f "${path}"
			fi
			echo "Removed ${path}" >&2
		done < <(find "${search_root}" "${FIND_EXPR[@]}")
	done
done

shopt -u nullglob dotglob
