"""
Plugin validation command for Dryade CLI.

Usage: dryade validate-plugin <path>

Validates:
1. Directory structure (required files exist)
2. Manifest schema (dryade.json)
3. Python syntax (plugin.py, routes.py)
4. Dependency declarations
5. UI build (if has_ui: true)
"""

import json
import sys
from pathlib import Path

import click

# Validation result codes
OK = 0
WARNING = 1
ERROR = 2

class ValidationResult:
    """Stores validation results."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warning(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def print_report(self):
        """Print validation report."""
        if self.info:
            for msg in self.info:
                click.echo(click.style(f"  [INFO] {msg}", fg="blue"))

        if self.warnings:
            for msg in self.warnings:
                click.echo(click.style(f"  [WARN] {msg}", fg="yellow"))

        if self.errors:
            for msg in self.errors:
                click.echo(click.style(f"  [ERROR] {msg}", fg="red"))

        if self.passed:
            click.echo(click.style("\n  Validation PASSED", fg="green", bold=True))
        else:
            click.echo(click.style("\n  Validation FAILED", fg="red", bold=True))

def validate_structure(plugin_path: Path, result: ValidationResult) -> dict | None:
    """Validate plugin directory structure."""
    click.echo("Checking structure...")

    # Required files
    required = ["dryade.json", "plugin.py"]
    for fname in required:
        if not (plugin_path / fname).exists():
            result.error(f"Missing required file: {fname}")

    # Optional but common files
    optional = ["routes.py", "schemas.py", "config.py", "__init__.py"]
    for fname in optional:
        if (plugin_path / fname).exists():
            result.add_info(f"Found optional file: {fname}")

    # Load manifest if exists
    manifest_path = plugin_path / "dryade.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            result.error(f"Invalid JSON in dryade.json: {e}")

    return None

def validate_manifest(manifest: dict, result: ValidationResult):
    """Validate manifest schema."""
    click.echo("Checking manifest...")

    # Required fields
    required_fields = ["name", "version", "description", "author"]
    for field in required_fields:
        if field not in manifest:
            result.error(f"Missing required manifest field: {field}")

    # Validate version format (semver-like)
    version = manifest.get("version", "")
    if version and not _is_valid_version(version):
        result.warning(f"Version '{version}' is not semver format (x.y.z)")

    # Validate name format
    name = manifest.get("name", "")
    if name:
        if not name.replace("_", "").replace("-", "").isalnum():
            result.error(f"Plugin name '{name}' contains invalid characters")
        if name.startswith("_") or name.startswith("-"):
            result.error("Plugin name cannot start with _ or -")

    # Check tier if specified
    tier = manifest.get("required_tier")
    if tier and tier not in ["starter", "team", "enterprise"]:
        result.warning(f"Unknown tier: {tier}")

    # Validate slots if present
    slots = manifest.get("slots", [])
    valid_slots = [
        "workflow-sidebar",
        "workflow-toolbar",
        "dashboard-widget",
        "chat-panel",
        "settings-section",
        "agent-detail-panel",
        "nav-footer",
        "modal-extension",
    ]
    for slot in slots:
        slot_name = slot.get("slot") if isinstance(slot, dict) else slot
        if slot_name not in valid_slots:
            result.warning(f"Unknown slot: {slot_name}")

def validate_python(plugin_path: Path, result: ValidationResult):
    """Validate Python syntax."""
    click.echo("Checking Python syntax...")

    py_files = list(plugin_path.glob("*.py"))
    for py_file in py_files:
        try:
            with open(py_file) as f:
                compile(f.read(), py_file, "exec")
            result.add_info(f"Syntax OK: {py_file.name}")
        except SyntaxError as e:
            result.error(f"Syntax error in {py_file.name}: {e}")

def validate_ui(plugin_path: Path, manifest: dict, result: ValidationResult):
    """Validate UI if has_ui: true."""
    if not manifest.get("has_ui"):
        return

    click.echo("Checking UI...")

    ui_path = plugin_path / "ui"
    if not ui_path.exists():
        result.error("has_ui is true but ui/ directory not found")
        return

    # Check package.json
    if not (ui_path / "package.json").exists():
        result.error("Missing ui/package.json")
    else:
        result.add_info("Found ui/package.json")

    # Check for built bundle
    dist_path = ui_path / "dist"
    if not dist_path.exists():
        result.warning("ui/dist/ not found - run 'npm run build' in ui/")
    elif not list(dist_path.glob("*.js")):
        result.warning("No .js files in ui/dist/ - build may have failed")
    else:
        result.add_info("Found built UI bundle")

def validate_dependencies(plugin_path: Path, result: ValidationResult):
    """Check for hardcoded core dependencies."""
    click.echo("Checking dependencies...")

    forbidden_imports = [
        "from core.ee.plugins_ee import PluginManager",
    ]

    py_files = list(plugin_path.glob("*.py"))
    for py_file in py_files:
        with open(py_file) as f:
            content = f.read()
            for forbidden in forbidden_imports:
                if forbidden in content:
                    result.error(f"{py_file.name} contains forbidden import: {forbidden}")

def _is_valid_version(version: str) -> bool:
    """Check if version is semver-like (x.y.z)."""
    parts = version.split(".")
    if len(parts) != 3:
        return False
    return all(part.isdigit() for part in parts)

@click.command("validate-plugin")
@click.argument("path", type=click.Path(exists=True))
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
@click.option("--quiet", "-q", is_flag=True, help="Only show errors")
def validate_plugin(path: str, strict: bool, quiet: bool):
    """
    Validate a Dryade plugin.

    PATH is the path to the plugin directory (containing dryade.json).

    Examples:
        dryade validate-plugin plugins/my-plugin
        dryade validate-plugin ./my-plugin --strict
    """
    plugin_path = Path(path)

    click.echo(f"\nValidating plugin: {plugin_path.name}")
    click.echo("=" * 50)

    result = ValidationResult()

    # Run all validations
    manifest = validate_structure(plugin_path, result)

    if manifest:
        validate_manifest(manifest, result)
        validate_ui(plugin_path, manifest, result)

    validate_python(plugin_path, result)
    validate_dependencies(plugin_path, result)

    # Print report
    if not quiet:
        click.echo("\n" + "=" * 50)
        result.print_report()

    # Exit code
    if not result.passed:
        sys.exit(ERROR)
    elif strict and result.warnings:
        click.echo(click.style("  (Strict mode: warnings treated as errors)", fg="yellow"))
        sys.exit(WARNING)
    else:
        sys.exit(OK)

if __name__ == "__main__":
    validate_plugin()
