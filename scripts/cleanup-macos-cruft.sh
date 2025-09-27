#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [[ ! -d "${ROOT_DIR}" ]]; then
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
  while IFS= read -r -d '' path; do
    if [[ -d "${path}" ]]; then
      rm -rf "${path}"
    else
      rm -f "${path}"
    fi
    echo "Removed ${path}" >&2
  done < <(find "${ROOT_DIR}" -path "*/.git" -prune -o -name "${pattern}" -print0)
done

shopt -u nullglob dotglob
