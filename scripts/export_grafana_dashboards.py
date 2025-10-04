#!/usr/bin/env python3
"""Export Grafana dashboards to JSON files for provisioning."""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to Python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from monitoring.dashboards import build_default_dashboards, export_dashboards


def main() -> int:
    """Export default Grafana dashboards."""
    
    dashboards = build_default_dashboards()
    destination = repo_root / "infra" / "grafana" / "dashboards"
    
    print(f"Exporting {len(dashboards)} dashboards to {destination}")
    
    exported = export_dashboards(dashboards, destination)
    
    for path in exported:
        print(f"  ✓ {path.name}")
    
    print(f"\n{len(exported)} dashboards exported successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
