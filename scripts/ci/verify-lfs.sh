#!/usr/bin/env bash
set -euo pipefail

if ! command -v git-lfs >/dev/null 2>&1; then
	echo "git-lfs not installed" >&2
	exit 2
fi

missing=$(git lfs ls-files 2>/dev/null | awk '$1 ~ /^-$/ {print}')
if [[ -n ${missing} ]]; then
	echo "Detected unhydrated LFS pointers:" >&2
	echo "${missing}" >&2
	echo "Attempting hydration..." >&2
	git lfs fetch --all
	git lfs checkout || git lfs pull || true
	missing_after=$(git lfs ls-files 2>/dev/null | awk '$1 ~ /^-$/ {print}')
	if [[ -n ${missing_after} ]]; then
		echo "ERROR: LFS hydration incomplete:" >&2
		echo "${missing_after}" >&2
		exit 3
	fi
fi

echo "LFS verification passed."
