#!/usr/bin/env bash
# shellformat shell=bash
set -euo pipefail

# Local helper to simulate the CI summary output to stdout
# Usage: bash scripts/summarize_dist.sh

GITHUB_SHA_LOCAL=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
RETENTION_DAYS_LOCAL=${RETENTION_DAYS:-30}

echo "## Build Artifacts Summary"
echo

echo "### Package Build"
printf -- "- **Git SHA**: \\`%s\\`\n" "${GITHUB_SHA_LOCAL}"
printf -- "- **Build Time**: \\`%s\\`\n" "$(date -u +"%Y-%m-%d %H:%M:%S UTC")"
echo

print_manifest_summary() {
  if [ -f dist/wheelhouse/manifest.json ]; then
    python -c "import json,sys;from pathlib import Path; p=Path('dist/wheelhouse/manifest.json'); data=json.loads(p.read_text()) if p.exists() else {}; s=[i for i in data.get('allow_sdist_used',[]) if i]; print('- **Source build fallback**: ⚠️ '+', '.join(sorted(set(s))) if s else '- **Source build fallback**: ✅ None')"
    echo
  else
    echo "- manifest.json not found"
    echo
  fi
}

if [ -d dist/wheelhouse ]; then
  wheel_count=$(find dist/wheelhouse -type f -name "*.whl" 2>/dev/null | wc -l | tr -d ' ')
  wheelhouse_size=$(du -sh dist/wheelhouse 2>/dev/null | cut -f1)
  echo "### Wheelhouse"
  printf -- "- **Wheel Count**: %s\n" "${wheel_count:-0}"
  printf -- "- **Total Size**: %s\n" "${wheelhouse_size:-0}"
  echo "- **Location**: \`dist/wheelhouse/\`"
  if find dist/wheelhouse -maxdepth 1 -type f -name "pip_audit*.whl" 2>/dev/null | grep -q .; then
    echo "- **Includes pip-audit**: ✅ Yes"
  else
    echo "- **Includes pip-audit**: ⚠️ No"
  fi
  # Wheel inventory (first 10)
  wheels_list=$(find dist/wheelhouse -maxdepth 1 -type f -name "*.whl" -printf "%f\n" 2>/dev/null | sort)
  if [ -n "${wheels_list}" ]; then
    echo "- **Wheel inventory**:"
    i=0
    total=0
    printf '%s
' "${wheels_list}" | while IFS= read -r w; do
      total=$((total+1))
      if [ $i -lt 10 ]; then
        echo "  - $w"
      fi
      i=$((i+1))
    done
    if [ $total -gt 10 ]; then
      echo "  - … and $(( total - 10 )) more"
    fi
  fi
  echo
  print_manifest_summary
else
  echo "### Wheelhouse"
  echo "- **Status**: ⚠️ Not found at \`dist/wheelhouse\`"
  echo
fi

if compgen -G "dist/*.whl" > /dev/null; then
  echo "### Python Wheel"
  echo "- Built successfully ✅"
  echo
else
  echo "### Python Wheel"
  echo "- **Status**: ⚠️ No wheel found in \`dist/\`"
  echo
fi

echo "### Dist Listing"
echo
echo '```text'
ls -lh dist/ 2>/dev/null || echo "(dist missing)"
echo '```'

echo
printf -- "All artifacts will be uploaded as \`app_bundle\` with %s-day retention.\n" "${RETENTION_DAYS_LOCAL}"
