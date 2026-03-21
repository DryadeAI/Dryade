# Plugin Testing Guide

This guide covers how to test Dryade plugins using the provided pytest fixtures.

## Setup

### Install Test Dependencies

```bash
pip install pytest pytest-asyncio pytest-cov
```

### Project Structure

```
my-plugin/
├── dryade.json
├── plugin.py
├── routes.py
└── tests/
    ├── __init__.py
    ├── conftest.py      # Import Dryade fixtures
    ├── test_plugin.py
    └── test_routes.py
```

### Configure pytest

Create `pytest.ini` or add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Import Fixtures

In your `tests/conftest.py`:

```python
# Import all Dryade testing fixtures
pytest_plugins = ['tests.community.conftest']
```

## Available Fixtures

### mock_llm

Mock LLM that returns configurable responses.

```python
def test_with_llm(mock_llm):
    # Default response
    response = await mock_llm.generate("Hello")
    assert response.content == "Mock response"

    # Check what was called
    assert mock_llm.calls[0]["prompt"] == "Hello"

    # Custom responses
    mock_llm.responses = ["Custom response"]
    response = await mock_llm.generate("Hello again")
    assert response.content == "Custom response"
```

### mock_llm_factory

Factory for creating mock LLMs with specific responses.

```python
def test_conversation(mock_llm_factory):
    llm = mock_llm_factory([
        "Nice to meet you",
        "I'm doing well",
        "Goodbye"
    ])

    # Responses cycle through in order
    r1 = await llm.generate("Hi")
    r2 = await llm.generate("How are you?")
    r3 = await llm.generate("Bye")

    assert r1.content == "Nice to meet you"
    assert r2.content == "I'm doing well"
    assert r3.content == "Goodbye"
```

### plugin_context

Provides standard plugin initialization context.

```python
async def test_plugin_init(plugin_context):
    from my_plugin import plugin

    await plugin.on_load(plugin_context)

    assert plugin.is_loaded
    assert plugin_context["settings"]["debug"] is True
```

### plugin_context_factory

Create custom contexts for specific test scenarios.

```python
def test_with_custom_settings(plugin_context_factory):
    ctx = plugin_context_factory(
        settings={
            "custom_option": True,
            "api_key": "test-key"
        },
        user={"id": "admin", "role": "admin"}
    )

    # Use in your plugin test
    await plugin.on_load(ctx)
```

### mock_db_session

Mock database session for testing database operations.

```python
def test_save_to_db(mock_db_session, plugin_context):
    plugin_context["db_session"] = mock_db_session

    # Your plugin code that adds to DB
    my_object = MyModel(name="test")
    mock_db_session.add(my_object)
    mock_db_session.commit()

    # Verify
    assert my_object in mock_db_session.added
    assert mock_db_session.committed
```

### mock_mcp_server

Mock MCP server for testing tool interactions.

```python
async def test_uses_mcp_tool(mock_mcp_server):
    # Register mock tool
    async def search_mock(query: str):
        return {"results": [f"Result for {query}"]}

    mock_mcp_server.register_tool("search", search_mock)

    # Call tool (as your plugin would)
    result = await mock_mcp_server.call_tool("search", query="test")

    assert "Result for test" in result["results"]
    assert mock_mcp_server.calls[0]["query"] == "test"
```

### mock_event_emitter

Track events emitted by your plugin.

```python
def test_emits_events(mock_event_emitter):
    # Your plugin emits events
    mock_event_emitter.emit("processing_started", {"file": "test.txt"})
    mock_event_emitter.emit("processing_complete", {"result": "success"})

    # Verify
    events = mock_event_emitter.get_events("processing_started")
    assert len(events) == 1
    assert events[0]["data"]["file"] == "test.txt"
```

### mock_request / mock_response

Mock FastAPI request/response for testing routes.

```python
async def test_api_route(mock_request, mock_response):
    from my_plugin.routes import get_status

    mock_request.query_params = {"include_details": "true"}

    result = await get_status(mock_request)

    assert result["status"] == "ok"
```

## Testing Patterns

### Testing Plugin Lifecycle

```python
import pytest

class TestMyPlugin:
    @pytest.mark.asyncio
    async def test_load_unload(self, plugin_context):
        from my_plugin import plugin

        # Initially not loaded
        assert not plugin.is_loaded

        # Load
        await plugin.on_load(plugin_context)
        assert plugin.is_loaded

        # Unload
        await plugin.on_unload()
        assert not plugin.is_loaded
```

### Testing API Routes

```python
from fastapi.testclient import TestClient
from my_plugin.routes import router

def test_status_endpoint():
    client = TestClient(router)
    response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

### Testing with Mocked Dependencies

```python
from unittest.mock import patch

async def test_with_mocked_external(mock_llm):
    with patch("my_plugin.plugin.get_llm", return_value=mock_llm):
        from my_plugin import plugin

        result = await plugin.process("input")

        # Verify LLM was called correctly
        assert "input" in mock_llm.calls[0]["prompt"]
```

### Testing Error Handling

```python
async def test_handles_llm_error(mock_llm_factory):
    async def raise_error(*args, **kwargs):
        raise Exception("LLM unavailable")

    mock_llm = mock_llm_factory()
    mock_llm.generate = raise_error

    with pytest.raises(Exception, match="LLM unavailable"):
        await plugin.process("input")
```

### Testing with Database Queries

```python
def test_query_results(mock_db_session):
    # Setup mock results
    mock_users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
    ]
    query = mock_db_session.query(User).with_results(mock_users)

    # Test query
    result = query.filter_by(name="Alice").first()

    # Verify query was built
    assert {"name": "Alice"} in query._filters
```

### Testing Async Functions

```python
import pytest

@pytest.mark.asyncio
async def test_async_function(mock_llm):
    """Test async plugin functions."""
    response = await mock_llm.generate("test")
    assert response.content == "Mock response"
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_plugin.py

# Run with coverage
pytest --cov=my_plugin --cov-report=html

# Run only async tests
pytest -m asyncio

# Run tests matching pattern
pytest -k "test_load"

# Run tests and stop on first failure
pytest -x
```

## CI Integration

Add to `.github/workflows/test.yml`:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov

      - name: Run tests
        run: pytest --cov=my_plugin --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### Coverage Thresholds

Add to `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["my_plugin"]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

## Best Practices

1. **Test in isolation** - Use mocks to avoid external dependencies
2. **Test both success and error paths** - Verify error handling works
3. **Keep tests fast** - Mocks should be faster than real services
4. **Use descriptive names** - `test_returns_error_when_invalid_input`
5. **One assertion concept per test** - Easier to debug failures
6. **Test edge cases** - Empty inputs, large inputs, special characters

### Fixture Composition

Combine fixtures for complex scenarios:

```python
@pytest.fixture
def configured_plugin(plugin_context, mock_llm, mock_mcp_server):
    """Fixture providing fully configured plugin."""
    plugin_context["llm"] = mock_llm
    plugin_context["mcp"] = mock_mcp_server
    return plugin_context
```

### Test Data Builders

Create helpers for common test data:

```python
def make_message(role="user", content="test"):
    return {"role": role, "content": content}

def test_with_messages():
    messages = [
        make_message("system", "You are helpful"),
        make_message("user", "Hello"),
    ]
    # Use messages in test
```

### Parametrized Tests

Test multiple scenarios efficiently:

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    assert input.upper() == expected
```

## Troubleshooting

### Tests hang indefinitely

Check for missing `await` on async calls or infinite loops in mocked functions.

### Fixture not found

Ensure `pytest_plugins = ['tests.community.conftest']` is in your conftest.py.

### Async tests not running

Add `@pytest.mark.asyncio` decorator and ensure `pytest-asyncio` is installed.

### Mock not being used

Verify patch targets the correct import path where the function is called, not where it's defined.

## See Also

- [Plugin Developer Guide](./PLUGIN-DEVELOPER-GUIDE.md) - Creating plugins
- [API Reference](./API.md) - Backend API documentation
- [Contributing Guide](./CONTRIBUTING.md) - Code contribution guidelines
