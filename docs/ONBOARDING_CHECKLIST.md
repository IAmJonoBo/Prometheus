# Contributor Onboarding Checklist

Welcome to Prometheus! This checklist will guide you from first clone to first contribution. Expected time: **30-45 minutes**.

## ✅ Pre-Flight

Before you start, ensure you have:

- [ ] **Python 3.11+** installed (`python --version`)
- [ ] **Git** installed and configured
- [ ] **GitHub account** with SSH key or PAT configured
- [ ] **Code editor** (VS Code recommended, see `.vscode/` for settings)
- [ ] **Docker** (optional, for services like Postgres, Qdrant)

---

## 📖 Phase 1: Orientation (5-10 minutes)

Get familiar with the project structure and goals.

- [ ] Read [README.md](../README.md) - Project overview
- [ ] Scan [CURRENT_STATUS.md](../CURRENT_STATUS.md) - What works today
- [ ] Review [Architecture Overview](docs/architecture.md) - System design
- [ ] Browse [Module Index](docs/MODULE_INDEX.md) - Find relevant modules
- [ ] Check [ROADMAP.md](docs/ROADMAP.md) - Near-term plans

**Key Concepts to Understand**:

- Prometheus is an **event-driven pipeline**: ingestion → retrieval → reasoning → decision → execution → monitoring
- Stages communicate via **immutable events** in `common/contracts/`
- The system works **offline-first** with optional external services

---

## 🛠️ Phase 2: Environment Setup (10-15 minutes)

Get your development environment running.

### 1. Clone Repository

```bash
git clone git@github.com:IAmJonoBo/Prometheus.git
cd Prometheus
```

- [ ] Repository cloned successfully

### 2. Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Or see [Poetry installation docs](https://python-poetry.org/docs/#installation).

- [ ] Poetry installed (`poetry --version`)

### 3. Install Dependencies

```bash
poetry install
```

This creates a virtual environment in `.venv/` and installs all dependencies.

- [ ] Dependencies installed without errors
- [ ] Virtual environment created (`.venv/` directory exists)

**Optional Extras**:

```bash
# For PII masking
poetry install --extras pii

# For LLM and RAG features
poetry install --extras "llm rag"
```

### 4. Activate Environment

```bash
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows
```

- [ ] Environment activated (prompt shows `(.venv)`)

### 5. Verify Installation

```bash
poetry run prometheus --help
```

You should see CLI help output.

- [ ] CLI command works

---

## 🧪 Phase 3: Run Tests (5 minutes)

Ensure everything works on your machine.

### 1. Run Unit Tests

```bash
poetry run pytest tests/unit/ -v
```

Expected: 164 passing, 11 failing (known issues tracked in TODO-refactoring.md)

- [ ] Tests run (some may fail - that's expected)

### 2. Check Coverage

```bash
poetry run pytest --cov=. --cov-report=term-missing
```

Expected: ~68% coverage

- [ ] Coverage report generated

### 3. Run Linting

```bash
poetry run ruff check .
```

- [ ] Linter runs (warnings are okay for now)

### 4. Type Checking (Optional)

```bash
poetry run mypy common/
```

- [ ] Type checker runs

---

## 🚀 Phase 4: Run the Pipeline (5 minutes)

Experience Prometheus in action.

### 1. Basic Pipeline Run

```bash
poetry run prometheus pipeline --query "configured"
```

This runs the full pipeline with sample data from `docs/samples/`.

- [ ] Pipeline completes successfully
- [ ] Output shows stages executing: ingestion → retrieval → reasoning → decision → execution → monitoring

### 2. Local-Only Profile

If you don't have external services running:

```bash
poetry run prometheus pipeline \
  --config configs/defaults/pipeline_local.toml \
  --query "test query"
```

- [ ] Pipeline runs in offline mode

### 3. Explore Output

Look for:

- Ingested documents in `var/ingestion.db` (if using SQLite)
- Logs in console showing stage progression
- Decision and execution results

- [ ] Understand the pipeline output

---

## 📝 Phase 5: Make Your First Change (10-15 minutes)

Let's make a small contribution to build confidence.

### 1. Pick a Task

Good first issues are labeled `good-first-issue` on GitHub. Or choose from:

**Documentation**:

- Fix a typo in any README
- Add an example to a docstring
- Improve a stage README

**Code**:

- Add a unit test for an uncovered function
- Fix a linting warning
- Improve error messages

**Select a task**:

- [ ] Task selected and understood

### 2. Create a Branch

```bash
git checkout -b fix/my-improvement
```

- [ ] Branch created

### 3. Make Changes

Edit the relevant files. Keep changes small and focused.

- [ ] Changes made
- [ ] Changes tested locally (`pytest`, `ruff check`)

### 4. Run Quality Checks

```bash
# Lint
poetry run ruff check .

# Format
poetry run ruff format .

# Test
poetry run pytest tests/unit/<relevant_test>.py

# Type check (if modifying common/)
poetry run mypy common/
```

- [ ] All checks pass (or existing issues unchanged)

### 5. Commit Changes

```bash
git add <changed_files>
git commit -m "fix: descriptive message"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation
- `test:` for tests
- `refactor:` for code refactoring

- [ ] Changes committed with good message

### 6. Push and Create PR

```bash
git push origin fix/my-improvement
```

Then create a PR on GitHub.

- [ ] PR created
- [ ] PR description explains the change
- [ ] CI checks are running

---

## 📚 Phase 6: Deep Dive (Optional)

Now that you're set up, explore areas of interest.

### Choose Your Path

**🔌 Ingestion Developer**

- [ ] Read [ingestion/README.md](../ingestion/README.md)
- [ ] Review connector implementations
- [ ] Try adding a new connector (filesystem, API, etc.)

**🔍 Retrieval Engineer**

- [ ] Read [retrieval/README.md](../retrieval/README.md)
- [ ] Understand hybrid search architecture
- [ ] Experiment with different embedding models

**🤖 Reasoning & LLM Integration**

- [ ] Read [reasoning/README.md](../reasoning/README.md)
- [ ] Review agent orchestration patterns
- [ ] Try integrating a local model (llama.cpp)

**🛡️ Decision & Policy**

- [ ] Read [decision/README.md](../decision/README.md)
- [ ] Understand policy evaluation flow
- [ ] Design a custom approval workflow

**⚙️ Execution & Integration**

- [ ] Read [execution/README.md](../execution/README.md)
- [ ] Explore Temporal workflow definitions
- [ ] Create a webhook adapter

**📊 Monitoring & Observability**

- [ ] Read [monitoring/README.md](../monitoring/README.md)
- [ ] Set up Grafana dashboards (`infra/`)
- [ ] Add custom metrics

---

## 🎯 Key Resources

### Documentation

- [Architecture](docs/architecture.md) - System design
- [Module Boundaries](docs/module-boundaries.md) - Module contracts
- [Testing Strategy](docs/TESTING_STRATEGY.md) - How to test
- [Developer Experience](docs/developer-experience.md) - Workflows
- [Contributing Guide](docs/CONTRIBUTING.md) - Contribution process

### Code

- [Common Contracts](../common/README.md) - Event schemas
- [Stage READMEs](docs/MODULE_INDEX.md) - Per-stage docs
- [ADRs](docs/ADRs/) - Architecture decisions

### Community

- [GitHub Issues](https://github.com/IAmJonoBo/Prometheus/issues) - Bugs and features
- [Discussions](https://github.com/IAmJonoBo/Prometheus/discussions) - Questions
- [CODEOWNERS](../CODEOWNERS) - Module owners

---

## 🚨 Troubleshooting

### Poetry issues

**Problem**: `poetry: command not found`  
**Fix**: Add Poetry to PATH or use `python3 -m poetry`

### Import errors

**Problem**: `ModuleNotFoundError: No module named 'prometheus'`  
**Fix**: Ensure virtual environment is activated and dependencies installed

### Test failures

**Problem**: Tests fail differently than CI  
**Fix**: Check Python version matches (3.11+), reinstall deps

### Docker services

**Problem**: Pipeline needs Postgres/Qdrant but I don't have them  
**Fix**: Use `pipeline_local.toml` config for offline mode

### Permission errors

**Problem**: Can't write to `var/` or `.cache/`  
**Fix**: Check directory permissions, create if missing

---

## ✨ You're Ready!

Congratulations! You've completed the onboarding checklist. You can now:

✅ Run the pipeline locally  
✅ Make and test changes  
✅ Submit pull requests  
✅ Navigate the codebase confidently

### Next Steps

1. **Find an Issue**: Check [good-first-issue](https://github.com/IAmJonoBo/Prometheus/labels/good-first-issue) label
2. **Join Discussions**: Ask questions, share ideas
3. **Review PRs**: Learn from others' contributions
4. **Update Docs**: Documentation is always appreciated

### Questions?

- 💬 [Start a Discussion](https://github.com/IAmJonoBo/Prometheus/discussions)
- 📧 Contact module owners (see CODEOWNERS)
- 📖 Check [docs/README.md](docs/README.md) for more guides

---

**Welcome to the team! 🎉**

_Last Updated: January 2025_
