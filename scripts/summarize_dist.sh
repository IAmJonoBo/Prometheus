#!/usr/bin/env bash
set -Eeuo pipefail
# Render a robust summary of dist/ contents to stdout
# Usage: scripts/summarize_dist.sh [dist_dir] >> "$GITHUB_STEP_SUMMARY"

DIST_DIR=${1:-dist}

printf "## Build Artifacts Summary\n\n"
printf "### Package Build\n"
printf "- **Git SHA**: \`%s\`\n" "${GITHUB_SHA:-unknown}"
printf "- **Build Time**: \`%s\`\n\n" "$(date -u +"%Y-%m-%d %H:%M:%S UTC")"

if [ -d "$DIST_DIR/wheelhouse" ]; then
  wheel_count=$(find "$DIST_DIR/wheelhouse" -type f -name "*.whl" 2>/dev/null | wc -l | tr -d ' ')
  wheelhouse_size=$(du -sh "$DIST_DIR/wheelhouse" 2>/dev/null | cut -f1)
  printf "### Wheelhouse\n"
  printf "- **Wheel Count**: %s\n" "${wheel_count:-0}"
  printf "- **Total Size**: %s\n" "${wheelhouse_size:-0}"
  printf "- **Location**: \`%s\`\n" "$DIST_DIR/wheelhouse/"
  if find "$DIST_DIR/wheelhouse" -maxdepth 1 -type f -name "pip_audit*.whl" 2>/dev/null | grep -q .; then
    printf "- **Includes pip-audit**: ✅ Yes\n"
  else
    printf "- **Includes pip-audit**: ⚠️ No\n"
  fi
  # Manifest-derived details
  if [ -f "$DIST_DIR/wheelhouse/manifest.json" ]; then
    DIST_DIR="$DIST_DIR" python - <<'PY'
import json
from pathlib import Path
import os
DIST = Path(os.environ.get('DIST_DIR', 'dist'))
p = DIST / 'wheelhouse' / 'manifest.json'
try:
    data = json.loads(p.read_text())
except Exception as e:
    print(f"- manifest.json parse error: {e}")
else:
    s=[item for item in data.get('allow_sdist_used', []) if item]
    print('- **Source build fallback**: ⚠️ ' + ', '.join(sorted(set(s))) if s else '- **Source build fallback**: ✅ None')
    # Wheel inventory (first 10)
    wheels=sorted([w.name for w in (DIST / 'wheelhouse').glob('*.whl')])
    if wheels:
        print('- **Wheel inventory**:')
        for w in wheels[:10]:
            print(f'  - {w}')
        if len(wheels) > 10:
            print(f'  - … and {len(wheels)-10} more')
PY
  fi
  printf "\n"
else
  printf "### Wheelhouse\n"
  printf "- **Status**: ⚠️ Not found at \`%s\`\n\n" "$DIST_DIR/wheelhouse"
fi

printf "### Python Wheel\n"
if compgen -G "$DIST_DIR/*.whl" > /dev/null; then
  printf "- Built successfully ✅\n\n"
else
  printf "- **Status**: ⚠️ No wheel found in \`%s\`\n\n" "$DIST_DIR"
fi

printf "### Dist Listing\n\n"
printf "```text\n"
ls -lh "$DIST_DIR" 2>/dev/null || echo "($DIST_DIR missing)"
printf "\n```\n"

printf "All artifacts will be uploaded as \`app_bundle\` with %s-day retention.\n" "${RETENTION_DAYS:-30}"
