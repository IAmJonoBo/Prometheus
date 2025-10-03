# Documentation Archive

This directory contains legacy and superseded documentation that has been replaced by more current content. These files are retained for historical reference but should not be used for current development.

## Archived Content

### Completed Initiatives
- `ARCHITECTURE_REFACTORING_REPORT.md` - Phase 1 refactoring completion report (superseded by ongoing TODO-refactoring.md)
- `Next Steps.md` - Legacy next steps (now tracked in TODO-refactoring.md and ROADMAP.md)
- `pipeline-optimization-summary.md` - Historical optimization summary
- `offline-packaging-status.md` - Point-in-time packaging status

### Superseded by Current Documentation
- `ci-workflow-comparison.md` - Replaced by `ci-handbook.md` and `CI/README.md`
- `dependency-upgrade-gap-analysis.md` - Consolidated into `dependency-governance.md`
- `dependency-upgrade-todos.md` - Tracked in TODO-refactoring.md
- `dependency-upgrade-tracker.md` - Now managed via Renovate and scripts

### Enhancement Planning (Completed or Ongoing)
- `orchestration-enhancement.md` - Features now documented in `orchestration-quickref.md`
- `offline-doctor-enhancements.md` - Enhancements integrated into scripts

## Using Archived Content

If you need to reference archived documentation:
1. Check if the information has been migrated to current docs via `docs/README.md`
2. Review the commit history to understand why it was archived
3. Consider whether the content should be restored or updated

## Migration Notes

Content was archived on 2025-01-XX as part of the project wrangling initiative to establish clear separation between:
- **Current** - Active, maintained documentation in `docs/`
- **Archive** - Historical/superseded content in `docs/archive/`
- **Future** - Planned features in `ROADMAP.md` and `FUTURE_ENHANCEMENTS.md`
