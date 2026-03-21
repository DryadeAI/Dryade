# Contributing to Dryade

Welcome! We're genuinely excited you want to contribute to Dryade. Whether this is your first contribution or your hundredth, every one matters -- and we'll help you succeed.

This guide gets you from "I want to help" to "my PR is merged" as quickly as possible.

Please review our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

---

## Getting Started

### Option A: Docker Compose (Recommended)

No Python environment setup needed -- just Docker.

```bash
# Fork and clone
git clone https://github.com/YOUR-USERNAME/Dryade.git
cd Dryade
cp .env.example .env
docker compose up -d
# Backend: http://localhost:8080
# Frontend: http://localhost:3000
```

That's it. Your dev environment is running.

### Option B: Manual Setup with uv

For developers who prefer working directly with Python:

```bash
git clone https://github.com/YOUR-USERNAME/Dryade.git
cd Dryade

# Backend
uv venv && source .venv/bin/activate
uv sync
cp .env.example .env

# Frontend
cd dryade-workbench
npm install
npm run dev
```

### Verify Your Setup

```bash
# Run backend tests
pytest tests/ -v

# Check backend linting
ruff check core/

# Check backend types
mypy core/

# Check frontend linting
cd dryade-workbench && npx eslint src/
```

If tests pass and linting is clean, you're ready to contribute!

---

## Good First Issues

New to the codebase? Look for issues labeled [`good-first-issue`](https://github.com/DryadeAI/Dryade/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue) -- we specifically mark these for newcomers.

Great first contributions:

- **Documentation improvements** -- typos, unclear explanations, missing examples
- **Test coverage** -- edge cases that aren't currently tested
- **Bug fixes with clear reproduction steps** -- when expected behavior is unambiguous
- **New LLM provider adapters** -- adding support for an OpenAI-compatible API
- **Quality-of-life improvements** -- better error messages, clearer logs

> Not sure where to start? Open a discussion or ask on [Discord](https://discord.gg/bvCPwqmu) -- we're happy to help you find the right starting point.

---

## Code Style

### Backend (Python)

- **Linter/formatter:** [Ruff](https://github.com/astral-sh/ruff) (line length 100, target Python 3.12)
- **Type checking:** [mypy](https://mypy-lang.org/) (strict mode)
- **Docstrings:** Google-style
- **Type hints:** Required on all public functions and methods

```python
def route_message(
    message: str,
    context: ExecutionContext,
    stream: bool = True,
) -> AsyncGenerator[ChatEvent, None]:
    """Route a message through the orchestrator.

    Args:
        message: The user message to process.
        context: Execution context with session and config.
        stream: Whether to stream the response.

    Returns:
        Async generator yielding chat events.

    Raises:
        RoutingError: If no suitable handler is found.
    """
```

### Frontend (TypeScript/React)

- **Linter:** [ESLint](https://eslint.org/) with TypeScript rules
- **Formatter:** Prettier
- **Style:** Functional components, hooks-based state management

### Pre-commit Hooks

Pre-commit hooks run automatically on every commit. They handle:

- **Ruff** -- Python linting and formatting (auto-fixes most issues)
- **mypy** -- Type checking
- **ESLint** -- Frontend linting
- **gitleaks** -- Secret detection

If a hook fails, fix the issue and re-commit. Most Ruff and ESLint issues are auto-fixed.

---

## Development Workflow

### Branch Naming

Create a feature branch from `main`:

```bash
git checkout -b feat/your-feature-name
```

Use descriptive prefixes:

- `feat/` -- New features (e.g., `feat/add-ollama-adapter`)
- `fix/` -- Bug fixes (e.g., `fix/websocket-reconnect`)
- `docs/` -- Documentation (e.g., `docs/update-deployment-guide`)
- `refactor/` -- Code cleanup (e.g., `refactor/simplify-router`)
- `test/` -- Test additions (e.g., `test/add-adapter-tests`)

### Running Tests

```bash
# All backend tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=core --cov-report=html

# Specific test file
pytest tests/test_router.py -v

# Frontend lint
cd dryade-workbench && npx eslint src/

# Frontend build check
cd dryade-workbench && npm run build
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

feat(router): add planner mode for dynamic flows
fix(adapter): handle null response from MCP server
docs(guide): update deployment instructions
test(orchestrator): add ReAct loop edge case tests
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

---

## Pull Request Process

### Before Submitting

- [ ] Linting passes: `ruff check core/`
- [ ] Type checking passes: `mypy core/`
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Type hints on all public functions
- [ ] Google-style docstrings on all public functions
- [ ] New behavior has test coverage

If you're unsure whether something meets the bar, submit the PR and ask -- we'd rather give feedback than have you abandon a good contribution.

### PR Description

Every pull request should include:

- A clear summary of the changes
- Why the change is needed
- How it was tested
- Any relevant issue numbers (e.g., `Closes #42`)

### Review Process

1. Submit your PR against the `main` branch
2. Automated checks (Ruff, mypy, pytest, ESLint, build) run automatically
3. A maintainer reviews your changes -- **we aim to review PRs within 48 hours**
4. Address any feedback
5. Once approved, a maintainer merges the PR

> If we're slow to review, ping us on [Discord](https://discord.gg/bvCPwqmu) -- we don't want PRs to languish.

### CLA Requirement

All contributors must agree to the [Contributor License Agreement](CLA.md) before their first PR is merged. The CLA uses a license-grant model (not copyright assignment) -- you retain full ownership of your contributions. By submitting a pull request, you automatically agree to the [CLA terms](CLA.md).

---

## Architecture Overview

A brief overview to help you navigate the codebase:

```
Dryade/
  core/                    # FastAPI backend
    api/                   #   REST + WebSocket endpoints
    orchestrator/          #   DryadeOrchestrator (ReAct loop)
    adapters/              #   Framework adapters (MCP, CrewAI, ADK, LangChain, A2A)
    auth/                  #   Authentication (JWT)
    db/                    #   Database models and persistence
  dryade-workbench/        # React/TypeScript frontend (Vite)
  agents/                  # Agent definitions
  skills/                  # Skills framework
  docs/                    # Documentation (rendered on dryade.ai)
  tests/                   # Test suite
```

**Key components:**

- **DryadeOrchestrator** -- The central ReAct loop with 3 execution modes (chat, planner, orchestrate)
- **HierarchicalToolRouter** -- Routes tool calls using semantic and regex matching across all connected MCP servers
- **Adapters** -- Translate framework-specific tool calling conventions into Dryade's internal protocol
- **Database** -- SQLite for development, PostgreSQL for production

---

## Issue Guidelines

### Bug Reports

When filing a bug report, include:

- **Steps to reproduce** -- Exact sequence to trigger the issue
- **Expected behavior** -- What you expected to happen
- **Actual behavior** -- What actually happened
- **Environment** -- OS, Python version, Docker version, browser
- **Logs** -- Relevant error output or stack traces

### Feature Requests

- **Describe the problem first** -- What are you trying to do?
- **Then propose a solution** -- How should Dryade solve this?
- **Consider alternatives** -- What other approaches did you consider?

### Security Vulnerabilities

Email [security@dryade.ai](mailto:security@dryade.ai) directly -- **do not open a public issue** for security vulnerabilities.

---

## What We Accept

- **Bug fixes** -- Fixes for any part of the codebase
- **Core platform improvements** -- Enhancements to the orchestrator, routing, adapters, and API
- **New adapters** -- Support for additional agent frameworks or LLM providers
- **Documentation** -- Improvements to guides, API docs, and examples
- **Test coverage** -- New tests, better edge case coverage, test infrastructure

## What We Don't Accept

The following areas are maintained by the Dryade team:

- **Plugin modifications** -- Plugins live in a separate repository and are maintained by the core team
- **Licensing changes** -- Changes to LICENSE, CLA, or licensing logic
- **Security-critical internals** -- The plugin loading system and authentication internals

If you find bugs in plugins, please open an issue rather than a PR.

---

## Community

- **Discord:** [discord.gg/bvCPwqmu](https://discord.gg/bvCPwqmu) -- questions, discussions, and connecting with other contributors
- **GitHub Discussions:** [Discussions](https://github.com/DryadeAI/Dryade/discussions) -- longer-form questions, ideas, and show-and-tell
- **Documentation:** [dryade.ai/docs](https://dryade.ai/docs) -- guides, API reference, and tutorials

### Community Guidelines

- Be respectful and constructive in all interactions
- Welcome contributors of all experience levels
- Focus feedback on the code, not the person
- Follow up on your PRs in a timely manner

---

## Contributor Recognition

Contributors are listed in our README and in release notes. Every merged PR gets a shout-out. Your name matters to us.

---

## License

Contributions to Dryade are made under the [Dryade Source Use License (DSUL)](LICENSE) per the [Contributor License Agreement](CLA.md). You retain full ownership of your contributions, including all moral rights.

---

Thank you for contributing to Dryade! Every contribution -- from a typo fix to a major feature -- makes the project better for everyone.
