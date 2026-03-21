# Playwright MCP Server

| Property | Value |
|----------|-------|
| **Package** | `@playwright/mcp@latest` |
| **Category** | Developer |
| **Transport** | STDIO |
| **Default** | Enabled |
| **Wrapper** | `core/mcp/servers/playwright.py` |

## Overview

The Playwright MCP Server provides browser automation capabilities using Microsoft's Playwright library. It enables agents to interact with web pages, take screenshots, generate PDFs, and analyze page accessibility.

### Key Features

- **Navigation**: Go to URLs, click elements, fill forms
- **Screenshots**: Capture full pages or specific elements
- **PDF Generation**: Create PDFs from web pages
- **Accessibility**: Get accessibility tree for LLM analysis
- **Cross-Browser**: Support for Chromium, Firefox, and WebKit

### When to Use

- E2E testing automation
- Screenshot generation for documentation
- Web scraping and data extraction
- Form filling automation
- Visual regression testing
- Accessibility auditing

## Configuration

Configuration in `config/mcp_servers.yaml`:

```yaml
playwright:
  enabled: true
  command:
    - npx
    - -y
    - '@playwright/mcp@latest'
  description: Browser automation for testing, screenshots, web interactions
  auto_restart: true
  max_restarts: 3
  timeout: 120.0  # Browser operations can be slow
```

### Advanced Configuration

The Python wrapper supports additional configuration:

```python
from core.mcp.servers.playwright import PlaywrightServer

# Custom configuration with browser selection
config = PlaywrightServer.get_config(
    headless=True,      # Run without visible browser
    browser="chromium"  # Options: chromium, firefox, webkit
)
```

### First Run Note

On first execution, Playwright downloads browser binaries (~200MB per browser). Subsequent runs use cached browsers and start faster.

To pre-install browsers:

```bash
npx playwright install chromium
npx playwright install firefox
npx playwright install webkit
```

## Tool Reference

### Navigation Tools

#### playwright_navigate

Navigate to a URL.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | The URL to navigate to |

**Returns**: void

```python
await pw.goto("https://example.com")
```

#### playwright_click

Click an element.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | string | Yes | CSS/text/role selector for element |

**Returns**: void

```python
await pw.click("button#submit")
await pw.click("text=Sign In")
```

#### playwright_fill

Fill an input field with text.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | string | Yes | CSS selector for input element |
| `value` | string | Yes | Text to fill |

**Returns**: void

```python
await pw.fill("input[name='email']", "user@example.com")
await pw.fill("#password", "secretpassword")
```

#### playwright_hover

Hover over an element.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | string | Yes | CSS selector for element |

**Returns**: void

```python
await pw.hover(".dropdown-trigger")
```

#### playwright_select_option

Select an option from a dropdown.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | string | Yes | CSS selector for select element |
| `value` | string | Yes | Value of option to select |

**Returns**: void

```python
await pw.select("select#country", "US")
```

### Screenshot & PDF Tools

#### playwright_screenshot

Capture a screenshot of the page or element.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fullPage` | boolean | No | Capture full scrollable page (default: false) |
| `selector` | string | No | Capture specific element instead of viewport |

**Returns**: Screenshot data (binary)

```python
# Capture viewport
screenshot = await pw.screenshot()
screenshot.save("viewport.png")

# Capture full page
screenshot = await pw.screenshot(full_page=True)
screenshot.save("fullpage.png")

# Capture specific element
screenshot = await pw.screenshot_element(".main-content")
screenshot.save("content.png")
```

#### playwright_pdf

Generate a PDF of the current page.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | Uses current page state |

**Returns**: PDF data (binary)

```python
pdf_data = await pw.pdf()
with open("page.pdf", "wb") as f:
    f.write(pdf_data)
```

### Accessibility & Info Tools

#### playwright_snapshot

Get the accessibility tree of the current page.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | Uses current page state |

**Returns**: Text representation of accessibility tree

```python
tree = await pw.get_accessibility_tree()
print(tree)
# Output shows semantic structure:
# - heading "Welcome"
# - button "Sign In"
# - link "Learn more"
```

#### playwright_get_title

Get the current page title.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | Uses current page state |

**Returns**: Page title string

```python
title = await pw.get_title()
print(f"Page title: {title}")
```

#### playwright_get_url

Get the current page URL.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | Uses current page state |

**Returns**: Current URL string

```python
url = await pw.get_url()
print(f"Current URL: {url}")
```

## Selector Strategies

Playwright supports multiple selector strategies for targeting elements:

### CSS Selectors

Standard CSS selectors for most cases:

```python
await pw.click("button.submit")           # Class selector
await pw.click("#login-form")             # ID selector
await pw.click("input[type='email']")     # Attribute selector
await pw.click("form > button")           # Child combinator
await pw.click(".card:first-child")       # Pseudo-selectors
```

### Text Selectors

Find elements by their visible text:

```python
await pw.click("text=Submit")             # Exact match
await pw.click("text=Sign")               # Partial match
await pw.click("text=/Submit|Send/i")     # Regex match
```

### Role Selectors

Find elements by ARIA role (best for accessibility):

```python
await pw.click("role=button[name='Submit']")
await pw.click("role=link[name='Learn more']")
await pw.click("role=checkbox[checked]")
await pw.fill("role=textbox[name='Email']", "user@example.com")
```

### XPath Selectors

Use XPath when CSS isn't sufficient:

```python
await pw.click("xpath=//button[@type='submit']")
await pw.click("xpath=//div[contains(@class, 'modal')]//button")
```

### Combining Selectors

Chain selectors for precise targeting:

```python
# CSS + text
await pw.click("article >> text=Read more")

# Within iframe
await pw.click("iframe >> button.submit")
```

## Python Wrapper Usage

The `PlaywrightServer` wrapper provides a typed Python interface:

```python
from core.mcp import get_registry
from core.mcp.servers import PlaywrightServer

# Get registry and create server wrapper
registry = get_registry()
pw = PlaywrightServer(registry)

# Complete workflow example
await pw.goto("https://example.com/login")
await pw.fill("input[name='email']", "user@example.com")
await pw.fill("input[name='password']", "password123")
await pw.click("button[type='submit']")

# Wait for navigation and verify
title = await pw.get_title()
assert "Dashboard" in title

# Take screenshot of result
screenshot = await pw.screenshot(full_page=True)
screenshot.save("dashboard.png")
```

### Data Types

```python
@dataclass
class Screenshot:
    data: bytes
    mime_type: str = "image/png"

    def save(self, path: str) -> None:
        """Save screenshot to file."""
        with open(path, "wb") as f:
            f.write(self.data)
```

## Common Use Cases

### E2E Testing

```python
# Login flow test
await pw.goto("https://app.example.com/login")
await pw.fill("#email", "test@example.com")
await pw.fill("#password", "testpass")
await pw.click("button[type='submit']")

# Verify redirect
url = await pw.get_url()
assert "/dashboard" in url
```

### Screenshot Documentation

```python
# Capture UI states for documentation
pages = [
    ("https://app.example.com/login", "login.png"),
    ("https://app.example.com/dashboard", "dashboard.png"),
    ("https://app.example.com/settings", "settings.png"),
]

for url, filename in pages:
    await pw.goto(url)
    screenshot = await pw.screenshot(full_page=True)
    screenshot.save(f"docs/images/{filename}")
```

### Web Scraping

```python
# Extract data using accessibility tree
await pw.goto("https://quotes.example.com")
tree = await pw.get_accessibility_tree()
# Parse tree to extract structured data
```

### Form Automation

```python
# Fill multi-step form
await pw.goto("https://app.example.com/signup")

# Step 1: Personal info
await pw.fill("#first-name", "John")
await pw.fill("#last-name", "Doe")
await pw.click("button:text('Next')")

# Step 2: Contact info
await pw.fill("#email", "john.doe@example.com")
await pw.fill("#phone", "+1234567890")
await pw.click("button:text('Submit')")
```

## Troubleshooting

### Common Errors

#### "Browser not found"

**Cause**: Browser binaries not installed.

**Solution**:
```bash
npx playwright install chromium
```

#### "Timeout exceeded"

**Cause**: Element not found within timeout period.

**Solution**:
1. Verify selector is correct
2. Increase timeout in configuration
3. Check if element is inside iframe
4. Ensure page has fully loaded

#### "Element not visible"

**Cause**: Element exists but is hidden or off-screen.

**Solution**:
1. Use `hover` to reveal hidden elements
2. Scroll element into view first
3. Check for overlapping elements

#### "Navigation timeout"

**Cause**: Page takes too long to load.

**Solution**:
1. Increase `timeout` in mcp_servers.yaml
2. Check network connectivity
3. Verify URL is accessible

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("core.mcp.servers.playwright").setLevel(logging.DEBUG)
```

## Performance Tips

1. **Reuse browser sessions** - Don't create new sessions for each operation
2. **Use headless mode** - Faster than headed mode in automation
3. **Prefer CSS selectors** - Faster than XPath
4. **Minimize screenshots** - Only capture when needed
5. **Use element screenshots** - Faster than full-page for specific areas

## Related Documentation

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
- [Playwright Documentation](https://playwright.dev/)
