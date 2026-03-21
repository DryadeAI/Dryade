"""
Plugin UI build commands for Dryade CLI.

Provides two commands:
  dryade build-plugins  -- discover plugins with has_ui=true and build missing UI bundles
  dryade dev-push       -- build plugins, then run dryade-pm push

Usage:
    dryade build-plugins
    dryade build-plugins --force
    dryade build-plugins --plugins-dir /path/to/plugins
    dryade build-plugins --plugin my_plugin --plugin other_plugin
    dryade dev-push
    dryade dev-push --force --plugins-dir /path/to/plugins

IMPORTANT: These commands compile TypeScript/React sources to JavaScript bundles.
They do NOT write ui_bundle_hash to dryade.json -- that is PM's responsibility.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

# Plugin tier directories for tiered layout
TIER_DIRS = {"starter", "team", "enterprise"}

# =============================================================================
# Internal helpers
# =============================================================================

def _find_ui_plugins(base: Path) -> list[tuple[Path, str]]:
    """Discover all plugin directories with has_ui=true.

    Supports both layouts:
      Flat layout:   <base>/my_plugin/dryade.json
      Tiered layout: <base>/starter/audio/dryade.json

    Returns:
        List of (plugin_dir, plugin_name) tuples.
    """
    results: list[tuple[Path, str]] = []

    if not base.is_dir():
        return results

    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue

        if child.name in TIER_DIRS:
            # Tiered layout: descend one more level
            for plugin_dir in sorted(child.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                manifest = plugin_dir / "dryade.json"
                if manifest.exists() and _has_ui(manifest):
                    results.append((plugin_dir, plugin_dir.name))
        else:
            # Flat layout: child is itself a plugin directory
            manifest = child / "dryade.json"
            if manifest.exists() and _has_ui(manifest):
                results.append((child, child.name))

    return results

def _has_ui(manifest_path: Path) -> bool:
    """Return True if the manifest declares has_ui: true."""
    try:
        with open(manifest_path) as f:
            data = json.load(f)
        return bool(data.get("has_ui", False))
    except (json.JSONDecodeError, OSError):
        return False

def _needs_build(plugin_dir: Path) -> bool:
    """Return True if the plugin's UI bundle is missing (needs to be built)."""
    ui_dir = plugin_dir / "ui"
    if not ui_dir.is_dir():
        return False

    dist_dir = ui_dir / "dist"
    if not dist_dir.is_dir():
        return True

    # Check for known output filenames
    for candidate in ("bundle.js", "plugin-ui.js"):
        if (dist_dir / candidate).exists():
            return False

    # Also check for any .js file in dist/ (some plugins use hashed names)
    if list(dist_dir.glob("*.js")):
        return False

    return True

def _build_plugin_ui(plugin_dir: Path, plugin_name: str) -> bool:
    """Run npm install + npm run build in the plugin's ui/ directory.

    Returns:
        True on success, False on failure.
    """
    ui_dir = plugin_dir / "ui"

    if not ui_dir.is_dir():
        click.echo(click.style(f"  [SKIP] {plugin_name}: no ui/ directory found", fg="yellow"))
        return True  # Not a build failure -- plugin has no ui/ to build

    if not (ui_dir / "package.json").exists():
        click.echo(click.style(f"  [ERROR] {plugin_name}: ui/package.json not found", fg="red"))
        return False

    # Step 1: npm install
    click.echo(f"  [....] {plugin_name}: npm install...")
    install_result = subprocess.run(
        ["npm", "install"],
        cwd=ui_dir,
        capture_output=True,
        text=True,
    )
    if install_result.returncode != 0:
        click.echo(click.style(f"  [FAIL] {plugin_name}: npm install failed", fg="red"))
        stderr_preview = install_result.stderr[:500] if install_result.stderr else "(no stderr)"
        click.echo(click.style(f"         {stderr_preview}", fg="red"))
        return False

    # Step 2: npm run build
    click.echo(f"  [....] {plugin_name}: npm run build...")
    build_result = subprocess.run(
        ["npm", "run", "build"],
        cwd=ui_dir,
        capture_output=True,
        text=True,
    )
    if build_result.returncode != 0:
        click.echo(click.style(f"  [FAIL] {plugin_name}: npm run build failed", fg="red"))
        stderr_preview = build_result.stderr[:500] if build_result.stderr else "(no stderr)"
        click.echo(click.style(f"         {stderr_preview}", fg="red"))
        return False

    click.echo(click.style(f"  [ OK ] {plugin_name}: bundle built", fg="green"))
    return True

def _invoke_build_plugins(
    plugins_dir: Path | None,
    force: bool,
    plugin_filter: tuple[str, ...],
) -> bool:
    """Core build logic, callable from both build-plugins and dev-push.

    Returns:
        True if all builds succeeded (or nothing needed building), False if any failed.
    """
    # Resolve plugins directory
    base = plugins_dir or Path("plugins")

    # Discover all UI plugins
    all_ui_plugins = _find_ui_plugins(base)

    if not all_ui_plugins:
        click.echo(click.style(f"No plugins with has_ui=true found in: {base}", fg="yellow"))
        return True

    # Filter by --plugin names if provided
    if plugin_filter:
        filter_set = set(plugin_filter)
        filtered = [(d, n) for (d, n) in all_ui_plugins if n in filter_set]
        unknown = filter_set - {n for (_, n) in all_ui_plugins}
        if unknown:
            click.echo(
                click.style(
                    f"Warning: unknown plugin(s): {', '.join(sorted(unknown))}", fg="yellow"
                )
            )
        all_ui_plugins = filtered

    built = 0
    skipped = 0
    failed = 0

    for plugin_dir, plugin_name in all_ui_plugins:
        if not force and not _needs_build(plugin_dir):
            click.echo(f"  [SKIP] {plugin_name}: dist/ already exists (use --force to rebuild)")
            skipped += 1
            continue

        success = _build_plugin_ui(plugin_dir, plugin_name)
        if success:
            built += 1
        else:
            failed += 1

    # Summary
    click.echo("")
    click.echo(f"Built: {built}, Skipped: {skipped}, Failed: {failed}")

    if failed:
        click.echo(
            click.style(
                "  Hint: re-run with --force to retry all, or --plugin <name> to target one.",
                fg="yellow",
            )
        )
        return False

    if built:
        click.echo("  Next step: dryade-pm push  (or: dryade dev-push)")

    return True

def _find_pm_binary() -> str | None:
    """Locate the dryade-pm binary.

    Search order:
      1. DRYADE_PM_PATH environment variable
      2. shutil.which("dryade-pm")
      3. Common install locations
    """
    # 1. Env var override
    env_path = os.environ.get("DRYADE_PM_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    # 2. PATH lookup
    which_result = shutil.which("dryade-pm")
    if which_result:
        return which_result

    # 3. Common install locations
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "dryade-pm",
        home / ".dryade" / "bin" / "dryade-pm",
        home / ".cargo" / "bin" / "dryade-pm",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None

# =============================================================================
# Click commands
# =============================================================================

@click.command("build-plugins")
@click.option(
    "--plugins-dir",
    "-d",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Path to the plugins directory (default: plugins/).",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Rebuild all bundles even if dist/ already exists.",
)
@click.option(
    "--plugin",
    "-p",
    "plugin_filter",
    multiple=True,
    metavar="NAME",
    help="Only build the specified plugin(s). Repeatable.",
)
def build_plugins(plugins_dir: Path | None, force: bool, plugin_filter: tuple[str, ...]):
    """Build UI bundles for all plugins that declare has_ui=true.

    Discovers plugins in a flat or tiered directory layout, skips any whose
    dist/ bundle already exists, and runs npm install + npm run build for the rest.

    \b
    Examples:
        dryade build-plugins
        dryade build-plugins --force
        dryade build-plugins --plugins-dir /path/to/plugins
        dryade build-plugins --plugin skill_editor --plugin audio
    """
    # Verify npm is available before doing anything
    if not shutil.which("npm"):
        click.echo(
            click.style(
                "Error: npm not found on PATH. Install Node.js first: https://nodejs.org",
                fg="red",
            )
        )
        sys.exit(1)

    base = plugins_dir or Path("plugins")
    click.echo(f"Building plugin UI bundles in: {base}")
    click.echo("=" * 60)

    success = _invoke_build_plugins(plugins_dir, force, plugin_filter)
    if not success:
        sys.exit(1)

@click.command("dev-push")
@click.option(
    "--plugins-dir",
    "-d",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Path to the plugins directory (default: plugins/).",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force rebuild all UI bundles before pushing.",
)
def dev_push(plugins_dir: Path | None, force: bool):
    """Build all plugin UI bundles, then run dryade-pm push.

    This is the complete dev workflow: compile UI sources and push a signed
    dev allowlist to the running Dryade core.

    \b
    Examples:
        dryade dev-push
        dryade dev-push --force
        dryade dev-push --plugins-dir /path/to/plugins
    """
    # Step 1: verify npm
    if not shutil.which("npm"):
        click.echo(
            click.style(
                "Error: npm not found on PATH. Install Node.js first: https://nodejs.org",
                fg="red",
            )
        )
        sys.exit(1)

    base = plugins_dir or Path("plugins")
    click.echo(f"[dev-push] Step 1/2: Building plugin UI bundles in: {base}")
    click.echo("=" * 60)

    build_ok = _invoke_build_plugins(plugins_dir, force, ())
    if not build_ok:
        click.echo(click.style("\nBuild failed -- not pushing to core.", fg="red"))
        sys.exit(1)

    # Step 2: find and invoke dryade-pm push
    click.echo("")
    click.echo("[dev-push] Step 2/2: Running dryade-pm push...")
    click.echo("=" * 60)

    pm_binary = _find_pm_binary()
    if pm_binary is None:
        click.echo(
            click.style(
                "Error: dryade-pm binary not found.\n"
                "  Install it from: https://dryade.ai/download\n"
                "  Or set the DRYADE_PM_PATH environment variable to its location.",
                fg="red",
            )
        )
        sys.exit(1)

    cmd = [pm_binary, "push"]
    if plugins_dir is not None:
        cmd += ["--plugins-dir", str(plugins_dir)]

    result = subprocess.run(cmd)
    sys.exit(result.returncode)
