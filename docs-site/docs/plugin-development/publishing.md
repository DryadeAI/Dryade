---
title: Publishing Plugins
sidebar_position: 5
---

# Publishing Plugins

This guide covers how to test your plugin locally, submit it to the Dryade marketplace, and manage releases.

## Local Development with Plugin CLI

During development, use the Plugin CLI to push a development allowlist that enables your plugin locally:

```bash
dryade-pm push --plugins-dir plugins/
```

This scans the specified directory, discovers all plugins with valid manifests, and pushes a development allowlist to your local Dryade instance. All discovered plugins become immediately available.

**Verify your plugin loaded:**

```bash
curl http://localhost:8000/api/plugins
```

You should see your plugin in the response list with its name, version, and status.

**Test your endpoints:**

```bash
curl http://localhost:8000/api/my_plugin/status
```

## Preparing for Publication

Before submitting to the marketplace, ensure your plugin meets these requirements:

### 1. Complete Manifest

Your `dryade.json` must include all required fields. Run validation:

```bash
dryade validate-plugin plugins/my_plugin --verbose
```

### 2. Passing Tests

All tests should pass:

```bash
pytest plugins/my_plugin/tests -v
```

### 3. Documentation

Include a `README.md` in your plugin directory covering:

- What the plugin does
- Configuration options
- Usage examples
- Any external service requirements (API keys, etc.)

### 4. UI Bundle (if applicable)

If your plugin has a UI, ensure the bundle is built and within the size limit:

```bash
cd plugins/my_plugin/ui
npm run build
ls -la dist/bundle.js
```

## Marketplace Submission

To distribute your plugin through the Dryade marketplace:

1. **Submit your plugin** -- Open a submission with your plugin repository or package at the marketplace
2. **Automated validation** -- The marketplace runs:
   - Manifest schema validation (all required fields, valid tier, semver version)
   - Security scan (no forbidden imports, no cross-plugin dependencies)
   - Test execution
3. **Review** -- The Dryade team reviews the submission for quality and security
4. **Publication** -- Approved plugins are signed and made available to users with the appropriate [license tier](/reference/tiers)

## Version Management

Follow semantic versioning (semver) for all releases:

| Change Type | Version Bump | Example |
|-------------|-------------|---------|
| Bug fixes, patches | PATCH | `1.0.0` to `1.0.1` |
| New features (backwards compatible) | MINOR | `1.0.1` to `1.1.0` |
| Breaking changes | MAJOR | `1.1.0` to `2.0.0` |

Update the version in both `dryade.json` and your plugin class:

```json
{
  "name": "my_plugin",
  "version": "1.1.0"
}
```

```python
class MyPlugin:
    version = "1.1.0"
```

### Release Workflow

1. Update the version number in `dryade.json` and `plugin.py`
2. Run all tests to confirm nothing is broken
3. Build the UI bundle if applicable
4. Tag the release in your repository:

```bash
git tag v1.1.0
git push origin v1.1.0
```

5. Submit the new version to the marketplace

## Sharing via GitHub

You can also share plugins directly via GitHub repositories:

1. Create a public repository for your plugin
2. Include installation instructions in your `README.md`
3. Tag releases with semver versions

Users can install your plugin by cloning it into their plugins directory:

```bash
git clone https://github.com/username/my-dryade-plugin.git plugins/my_plugin
```

Then push the development allowlist to load it:

```bash
dryade-pm push --plugins-dir plugins/
```

## Plugin Tier Guidelines

When choosing the `required_tier` for your plugin:

| Tier | Best For |
|------|----------|
| **starter** | General-purpose utilities, basic integrations, developer tools |
| **team** | Collaboration features, advanced analytics, team workflows |
| **enterprise** | Compliance tools, audit logging, SSO integrations, advanced security |

See [Plans & Features](/reference/tiers) for a full comparison of what each tier includes.

## Getting Help

For questions about plugin development and publishing:

- **GitHub Discussions**: [github.com/DryadeAI/Dryade/discussions](https://github.com/DryadeAI/Dryade/discussions)
- **Email**: [plugins@dryade.ai](mailto:plugins@dryade.ai)
