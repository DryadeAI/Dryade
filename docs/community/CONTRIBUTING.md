# Contributing to Dryade

Thank you for your interest in contributing to Dryade! This document provides guidelines for contributing to the community edition.

## Ways to Contribute

- **Bug Reports**: Found a bug? Open an issue with reproduction steps
- **Feature Requests**: Have an idea? Start a discussion
- **Code Contributions**: Fix bugs, add features, improve docs
- **Documentation**: Improve or translate documentation
- **Plugins**: Create and share community plugins

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please be respectful in all interactions.

## Getting Started

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/YOUR-USERNAME/dryade.git
cd dryade

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests
pytest
```

### Project Structure

```
dryade/
├── core/               # Core application code
│   ├── api/           # FastAPI routes
│   ├── orchestrator/  # Agent orchestration
│   ├── plugins/       # Plugin loader
│   └── skills/        # Skills framework
├── plugins/           # Community plugins
├── dryade-workbench/  # React frontend
├── docs/              # Documentation
├── tests/             # Test suite
└── scripts/           # Utility scripts
```

## Making Changes

### Branch Naming

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring

Example: `feature/add-webhook-support`

### Commit Messages

Follow conventional commits:

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:
```
feat(plugins): add webhook notification plugin
fix(api): handle empty response from MCP server
docs(readme): update installation instructions
```

### Code Style

- Python: Follow PEP 8, use Ruff for linting
- TypeScript: Follow project ESLint config
- Run `ruff check` before committing
- Run `pytest` before submitting PR

### Testing

- Write tests for new features
- Maintain or improve coverage
- Test both success and error paths

```bash
# Run all tests
pytest

# Run specific tests
pytest tests/unit/test_plugins.py

# Run with coverage
pytest --cov=core
```

## Pull Request Process

### Before Submitting

1. **Check existing issues** - Is there already work on this?
2. **Create an issue** - For significant changes, discuss first
3. **Write tests** - PRs without tests may be delayed
4. **Run linting** - `ruff check` must pass
5. **Update docs** - If behavior changes, update docs

### Submitting

1. Create a branch from `main`
2. Make your changes
3. Push to your fork
4. Open a Pull Request

### PR Template

```markdown
## Description
[What does this PR do?]

## Related Issue
Fixes #123

## Changes
- Added X
- Changed Y
- Fixed Z

## Testing
[How was this tested?]

## Screenshots
[If UI changes]
```

### Review Process

1. Maintainers will review within 1-2 weeks
2. Address feedback or explain your approach
3. Once approved, a maintainer will merge
4. Your contribution will be in the next release!

## Plugin Contributions

See [Plugin Developer Guide](./PLUGIN-DEVELOPER-GUIDE.md) for creating plugins.

### Community Plugins

Community plugins can be:
- Added to the main repo (if generally useful)
- Shared in your own repo (link in discussions)
- Published to the future marketplace

To add a plugin to the main repo:
1. Follow the plugin structure guidelines
2. Include tests
3. Add documentation
4. Submit a PR

## Documentation Contributions

Documentation improvements are always welcome!

### Types of Doc Changes

- Fix typos or clarify wording
- Add examples
- Improve code samples
- Add missing documentation
- Translate documentation

### Doc Structure

```
docs/community/
├── README.md              # Main entry point
├── QUICK-START.md         # Getting started
├── PLUGIN-DEVELOPER-GUIDE.md
├── CONTRIBUTING.md        # (this file)
├── TROUBLESHOOTING.md
├── MCP-SERVERS.md
└── API-REFERENCE.md
```

## Getting Help

- **Discussions**: [GitHub Discussions](https://github.com/dryade/dryade/discussions)
- **Discord**: Coming soon
- **Issues**: For bugs and feature requests

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (Sustainable Use License).

## Recognition

Contributors are recognized in:
- Release notes
- Contributors list in README
- (Future) Community spotlight

Thank you for making Dryade better!
