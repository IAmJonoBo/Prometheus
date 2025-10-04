#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PATTERNS=(
	"-name" ".DS_Store"
	"-o" "-name" ".AppleDouble"
	"-o" "-name" "._*"
	"-o" "-name" "Icon?"
	"-o" "-name" "__MACOSX"
)

mapfile -d '' MATCHES < <(find "${ROOT_DIR}" -path "*/.git" -prune -o "${PATTERNS[@]}" -print0)

if [[ ${#MATCHES[@]} -eq 0 ]]; then
	exit 0
fi

printf 'Detected %d macOS metadata artefacts:\n' "${#MATCHES[@]}" >&2
for path in "${MATCHES[@]}"; do
	printf '  %s\n' "${path}" >&2
done

echo "Run scripts/cleanup-macos-cruft.sh to remove them before committing." >&2
exit 1
