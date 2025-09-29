#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=""
INCLUDE_GIT=false

usage() {
	cat <<'EOF'
Usage: cleanup-macos-cruft.sh [--include-git] [ROOT_DIR]

Removes macOS metadata artefacts (e.g., .DS_Store, AppleDouble) from the
workspace. By default, .git directories are skipped. Pass --include-git to
purge AppleDouble files that may have been copied into the repository metadata
folder (useful after extracting archives with Finder).
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--include-git)
		INCLUDE_GIT=true
		shift
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

PATTERNS=(
	".DS_Store"
	"._*"
	".AppleDouble"
	"Icon?"
	"__MACOSX"
)

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
	done < <(find "${ROOT_DIR}" "${FIND_EXPR[@]}")
done

shopt -u nullglob dotglob
