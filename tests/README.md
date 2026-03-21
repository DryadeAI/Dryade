# Dryade Test Suite

This directory contains all tests for the Dryade project.

## Directory Structure

```
tests/
├── conftest.py         # Shared fixtures (all tests)
├── unit/               # Unit tests
│   ├── conftest.py     # Unit-specific fixtures
│   ├── plugins/        # Plugin tests
│   └── test_*.py       # Core module tests
├── integration/        # Integration tests
│   └── test_*.py       # API, service tests
├── e2e/                # End-to-end tests
│   └── test_*.py       # Full workflow tests
└── agents/             # Agent-specific tests
    └── test_*.py
```

## Quick Commands

```bash
# Run all unit tests (fastest)
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=core --cov=plugins --cov-report=term-missing

# Run integration tests
pytest tests/integration/

# Run specific test file
pytest tests/unit/test_config.py -v

# Run tests matching a pattern
pytest tests/ -k "test_auth"

# Stop on first failure
pytest tests/unit/ -x

# Run tests by marker
pytest tests/ -m unit
pytest tests/ -m integration
pytest tests/ -m "not slow"
```

## Test Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.unit` | Fast, isolated unit tests |
| `@pytest.mark.integration` | Tests using real services |
| `@pytest.mark.e2e` | End-to-end workflow tests |
| `@pytest.mark.slow` | Long-running tests |
| `@pytest.mark.requires_llm` | Tests needing LLM service |
| `@pytest.mark.requires_mcp` | Tests needing MCP server |

## Naming Conventions

- **Files**: `test_<module_name>.py`
- **Classes**: `Test<ClassName>` or `Test<Functionality>`
- **Functions**: `test_<what_is_being_tested>`

```python
class TestAuthService:
    def test_authenticate_valid_credentials(self):
        ...
```

## Key Fixtures

### From `tests/conftest.py`

- `mock_settings` - Test configuration
- `mock_llm` - Mock LLM client
- `test_app` - FastAPI TestClient
- `db_session` - In-memory database session
- `test_app_with_db` - TestClient with DB

### From `tests/unit/conftest.py`

- `mock_extension_registry` - Empty extension registry
- `mock_context_store` - Pre-populated context store
- `mock_state_store` - State store with test data

## Writing Tests

### Basic Test

```python
def test_config_loads_defaults(mock_settings):
    assert mock_settings.env == "development"
    assert mock_settings.debug is True
```

### Async Test

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result == expected
```

### API Test

```python
def test_health_endpoint(test_app):
    response = test_app.get("/health")
    assert response.status_code == 200
```

### Database Test

```python
def test_create_record(db_session):
    from core.database.models import User
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
```

## Troubleshooting

### ModuleNotFoundError

```bash
# Install in development mode
pip install -e .

# Or set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Async Warnings

```bash
pip install pytest-asyncio
```

### Find Slow Tests

```bash
pytest tests/ --durations=10
```

## Full Documentation

See [Testing Guide](../docs_site/development/testing.md) for complete documentation.
