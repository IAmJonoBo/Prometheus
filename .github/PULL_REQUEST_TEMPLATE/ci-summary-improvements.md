## CI Summary Improvements

This PR improves the GitHub Actions workflow summary for build artifacts and adds a local helper script to preview the summary.

Changes

- Improve formatting and robustness of the "Build Artifacts Summary" in CI
- Ensure consistent newlines and always-present sections with clear statuses
- Add wheel inventory (first 10) when wheelhouse is present
- Add scripts/summarize_dist.sh to simulate the summary output locally

How to test locally

- Run: bash scripts/summarize_dist.sh
- Observe the Markdown summary printed to stdout

Expected CI behavior

- GitHub Actions summary contains:
  - Header, Git SHA, Build Time
  - Wheelhouse section (or Not found status)
  - Python Wheel section (success or Not found)
  - Dist listing code block
  - Final artifact retention note

Checklist

- [ ] CI run displays the improved summary in the job summary
- [ ] No functional changes to build/publish steps
- [ ] Summary renders correctly when artifacts are absent
