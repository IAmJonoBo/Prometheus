# Project Organization Summary

This document provides a bird's-eye view of how Prometheus is organized and where to find information.

## 🗺️ Navigation Map

### For First-Time Contributors
1. **[README.md](README.md)** - Start here: project overview and quick links
2. **[CURRENT_STATUS.md](CURRENT_STATUS.md)** - What works today vs. what's planned
3. **[docs/ONBOARDING_CHECKLIST.md](docs/ONBOARDING_CHECKLIST.md)** - Step-by-step setup (30-45 min)
4. **[docs/getting-started.md](docs/getting-started.md)** - Detailed environment setup

### For Understanding the System
1. **[docs/overview.md](docs/overview.md)** - Executive summary and goals
2. **[docs/architecture.md](docs/architecture.md)** - Technical design and event flows
3. **[docs/MODULE_INDEX.md](docs/MODULE_INDEX.md)** - Index of all 25 modules
4. **[docs/module-boundaries.md](docs/module-boundaries.md)** - Module contracts and dependencies

### For Product Context
1. **[Prometheus Brief.md](Prometheus Brief.md)** - Original vision and requirements (116KB)
2. **[FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md)** - Long-term roadmap
3. **[docs/ROADMAP.md](docs/ROADMAP.md)** - Near-term committed work
4. **[docs/tech-stack.md](docs/tech-stack.md)** - Technology choices and rationale

### For Contributors
1. **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** - How to contribute
2. **[docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md)** - Testing guidelines
3. **[docs/developer-experience.md](docs/developer-experience.md)** - Development workflows
4. **[TODO-refactoring.md](TODO-refactoring.md)** - Open tasks and technical debt
5. **[CODEOWNERS](CODEOWNERS)** - Module ownership

### For Copilot Agents
1. **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - Agent guidelines
2. **[AGENTS.md](AGENTS.md)** - Quick orientation for AI assistants

---

## 📁 Directory Structure

```
Prometheus/
├── 📄 README.md                    # Project overview
├── 📄 CURRENT_STATUS.md            # Project health dashboard
├── 📄 FUTURE_ENHANCEMENTS.md       # Long-term vision
├── 📄 TODO-refactoring.md          # Technical debt tracker
├── 📄 Prometheus Brief.md          # Original product vision
├── 📄 AGENTS.md                    # AI agent instructions
│
├── 📂 docs/                        # All documentation
│   ├── 📄 README.md                # Documentation index
│   ├── 📄 MODULE_INDEX.md          # All modules indexed
│   ├── 📄 ONBOARDING_CHECKLIST.md  # First contribution guide
│   ├── 📄 TESTING_STRATEGY.md      # Testing guide
│   ├── 📄 getting-started.md       # Setup instructions
│   ├── 📄 architecture.md          # System design
│   ├── 📄 ROADMAP.md               # Near-term plans
│   ├── 📂 ADRs/                    # Architecture decisions
│   └── 📂 archive/                 # Legacy docs
│
├── 📂 ingestion/                   # Stage 1: Data ingestion
├── 📂 retrieval/                   # Stage 2: Search & context
├── 📂 reasoning/                   # Stage 3: Analysis & synthesis
├── 📂 decision/                    # Stage 4: Policy & approval
├── 📂 execution/                   # Stage 5: Action dispatch
├── 📂 monitoring/                  # Stage 6: Telemetry & feedback
│
├── 📂 common/                      # Shared contracts & utilities
├── 📂 model/                       # Model management
├── 📂 observability/               # Telemetry & tracing
├── 📂 security/                    # Auth & data protection
├── 📂 governance/                  # Compliance & audit
│
├── 📂 api/                         # REST API (FastAPI)
├── 📂 prometheus/                  # CLI (Typer)
├── 📂 sdk/                         # Python client library
│
├── 📂 web/                         # Next.js UI (placeholder)
├── 📂 desktop/                     # Tauri app (placeholder)
├── 📂 ux/                          # Design & accessibility
├── 📂 collaboration/               # CRDT & real-time (planned)
│
├── 📂 plugins/                     # Optional extensions
├── 📂 tests/                       # Test suite
├── 📂 configs/                     # Configuration profiles
├── 📂 infra/                       # Docker Compose stacks
├── 📂 scripts/                     # Build & automation
└── 📂 vendor/                      # Vendored dependencies
```

---

## 🎯 Content Organization

### Current vs. Archive vs. Future

**Current** (Active, Maintained)
- Main README and documentation in `docs/`
- Stage READMEs co-located with code
- ADRs documenting accepted decisions
- CURRENT_STATUS.md reflecting actual state

**Archive** (`docs/archive/`)
- Completed initiative reports
- Superseded documentation
- Historical planning docs
- See [docs/archive/README.md](docs/archive/README.md)

**Future** (Planned)
- FUTURE_ENHANCEMENTS.md - Long-term vision
- ROADMAP.md - Near-term commitments
- TODO-refactoring.md - Technical improvements
- Open GitHub issues and discussions

---

## 📊 Documentation Hierarchy

### Level 1: Orientation (Start Here)
- README.md
- CURRENT_STATUS.md
- docs/overview.md

### Level 2: Understanding (Concepts)
- docs/architecture.md
- docs/MODULE_INDEX.md
- docs/tech-stack.md
- Prometheus Brief.md

### Level 3: Contributing (Hands-On)
- docs/ONBOARDING_CHECKLIST.md
- docs/getting-started.md
- docs/CONTRIBUTING.md
- docs/TESTING_STRATEGY.md

### Level 4: Deep Dive (Specific Areas)
- Stage READMEs (ingestion/, retrieval/, etc.)
- docs/module-boundaries.md
- docs/ADRs/
- Source code with inline documentation

### Level 5: Operations (Running in Production)
- docs/observability.md
- docs/performance.md
- docs/quality-gates.md
- infra/README.md

---

## 🔍 Finding Information

### "How do I...?"

**Set up my environment?**
→ [docs/getting-started.md](docs/getting-started.md)

**Make my first contribution?**
→ [docs/ONBOARDING_CHECKLIST.md](docs/ONBOARDING_CHECKLIST.md)

**Understand the architecture?**
→ [docs/architecture.md](docs/architecture.md)

**Find a specific module?**
→ [docs/MODULE_INDEX.md](docs/MODULE_INDEX.md)

**Write tests?**
→ [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md)

**Add an ingestion connector?**
→ [ingestion/README.md](ingestion/README.md)

**Improve search quality?**
→ [retrieval/README.md](retrieval/README.md)

**Integrate an LLM?**
→ [reasoning/README.md](reasoning/README.md) + [model/README.md](model/README.md)

**Deploy to production?**
→ [infra/README.md](infra/README.md) + [docs/observability.md](docs/observability.md)

**Understand a design decision?**
→ [docs/ADRs/](docs/ADRs/)

**See what's planned?**
→ [docs/ROADMAP.md](docs/ROADMAP.md) + [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md)

**Report a bug?**
→ [GitHub Issues](https://github.com/IAmJonoBo/Prometheus/issues)

**Ask a question?**
→ [GitHub Discussions](https://github.com/IAmJonoBo/Prometheus/discussions)

---

## 🏗️ Architectural Principles

### Event-Driven Pipeline
- Six stages: ingestion → retrieval → reasoning → decision → execution → monitoring
- Stages communicate via immutable events in `common/contracts/`
- Each stage can scale independently

### Offline-First
- Works without external services (degraded mode)
- Optional integrations with Postgres, OpenSearch, Qdrant, Temporal
- Models can run locally (quantized) or via API

### OSS-First
- Prefer open-source over proprietary
- Cloud providers are opt-in plugins
- Self-hostable on-premises

### Modular & Extensible
- Plugin system for optional capabilities
- Clear module boundaries (see [docs/module-boundaries.md](docs/module-boundaries.md))
- Adapter pattern for integrations

---

## 📈 Project Metrics

**Lines of Code**: ~50K+ Python, ~5K TypeScript (UI placeholders)  
**Documentation**: ~150 pages across 45+ markdown files  
**Test Coverage**: 68% (target: 80%)  
**Modules**: 25 distinct modules with READMEs  
**ADRs**: 3 architecture decision records  
**Contributors**: See GitHub insights  

---

## 🔄 Keeping Documentation Current

### When to Update

**Code Changes**:
- Update relevant stage README if behavior changes
- Add/update ADR for architectural decisions
- Update module-boundaries.md if contracts change

**Feature Complete**:
- Move item from FUTURE_ENHANCEMENTS.md to CURRENT_STATUS.md
- Update ROADMAP.md if milestones shift
- Document in stage README and tests

**Bug Fixed**:
- Update CURRENT_STATUS.md if known issue resolved
- Remove from TODO-refactoring.md if tracked there

**New Module**:
- Add README to module directory
- Update MODULE_INDEX.md
- Update dependency-graph.md if applicable
- Add to CODEOWNERS

### Documentation Review Checklist

- [ ] README.md reflects current capabilities
- [ ] CURRENT_STATUS.md is accurate
- [ ] Stage READMEs match implementation
- [ ] ADRs document significant decisions
- [ ] Module boundaries are clear
- [ ] Tests document expected behavior
- [ ] Examples work as shown

---

## 🎓 Learning Path

### Week 1: Foundation
1. Clone repo and run pipeline
2. Read architecture and module index
3. Run tests and understand coverage
4. Make a small documentation fix (PR #1)

### Week 2: Deep Dive
1. Pick a stage of interest
2. Read stage README and source
3. Add unit tests to improve coverage
4. Implement a small feature (PR #2)

### Week 3: Integration
1. Understand event flows across stages
2. Write integration tests
3. Add a connector or adapter
4. Review others' PRs

### Month 2+: Ownership
1. Take ownership of a module (CODEOWNERS)
2. Review PRs affecting your area
3. Mentor new contributors
4. Shape roadmap and architecture

---

## 📝 Contributing to Documentation

Documentation improvements are always welcome! Focus areas:

1. **Clarify existing docs** - Fix typos, improve explanations
2. **Add examples** - Code snippets, configuration examples
3. **Fill gaps** - Document undocumented features
4. **Update outdated content** - Keep current with code
5. **Improve navigation** - Better cross-linking, indexing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for process.

---

## 🆘 Getting Help

**Stuck?** Try these in order:

1. **Search documentation** - Use site search or grep
2. **Check MODULE_INDEX.md** - Find relevant module
3. **Read stage README** - Detailed module docs
4. **Search GitHub Issues** - Someone may have asked before
5. **Ask in Discussions** - Community Q&A
6. **Contact module owner** - See CODEOWNERS

**Found a bug?**
→ [Open an Issue](https://github.com/IAmJonoBo/Prometheus/issues/new)

**Have an idea?**
→ [Start a Discussion](https://github.com/IAmJonoBo/Prometheus/discussions/new?category=ideas)

---

**Last Updated**: January 2025  
**Maintainers**: All contributors (see CODEOWNERS)

This document is part of the living documentation and should be updated as the project evolves.
