# Pain Points Log

Use this log to capture recurring friction so the team can prioritise fixes.
Each entry should follow the standard template below.

```text
- id: PPL-YYYY-MM-DD-###
  category: build|test|docs|tooling|ux|infra|automation|security|other
  title: <short, action-biased>
  trigger: <what surfaced the issue>
  impact_minutes_per_week: <integer>
  frequency: daily|weekly|per-PR|ad-hoc
  confidence: 0.0-1.0
  repro_steps: <list or link>
  current_workaround: <text>
  root_cause_hypothesis: <text>
  research_notes: <summary + links>
  references: [<urls>]
  proposed_fix: <text>
  helper_or_tooling_changes: <files or modules to touch>
  tests_required: <unit|integration|e2e + brief>
  status: logged|researched|planned|in-progress|landed|wontfix
  follow_up_issue: <tracker link>
```

## Usage guidelines

- Log a new entry whenever a CI check fails twice for the same reason in a
  week, a manual step repeats three or more times, reviews surface recurring
  comments, a flaky test is quarantined, or an incident/regression is resolved.
- Reference the relevant ADR, roadmap item, or issue whenever an entry drives a
  significant change.
- Update `status` as work progresses and close the loop by linking the final fix.
