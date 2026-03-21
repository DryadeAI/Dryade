"""
Plugin creation command for Dryade CLI.

Usage: dryade create-plugin <name> [options]

Creates a new plugin with the standard directory structure and required files.
"""

import shutil
import subprocess
from pathlib import Path

import click

MANIFEST_TEMPLATE = """{{
    "name": "{name}",
    "version": "0.1.0",
    "description": "{description}",
    "author": "{author}",
    "required_tier": "starter",
    "has_ui": {has_ui},
    "api_paths": [{api_paths}],
    "slots": []
}}
"""

PLUGIN_TEMPLATE = '''"""
{name} plugin for Dryade.

{description}
"""

from typing import Any

class {class_name}Plugin:
    """Main plugin class."""

    name = "{name}"
    version = "0.1.0"

    def __init__(self):
        """Initialize the plugin."""
        self._loaded = False

    async def on_load(self, context: dict[str, Any]) -> None:
        """Called when the plugin is loaded.

        Args:
            context: Plugin context with app, settings, etc.
        """
        self._loaded = True
        # Add initialization logic here

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded."""
        self._loaded = False
        # Add cleanup logic here

    @property
    def is_loaded(self) -> bool:
        """Check if plugin is loaded."""
        return self._loaded

# Plugin instance
plugin = {class_name}Plugin()
'''

ROUTES_TEMPLATE = '''"""
API routes for {name} plugin.
"""

from fastapi import APIRouter, Depends

router = APIRouter(prefix="/{name}", tags=["{name}"])

@router.get("/status")
async def get_status():
    """Get plugin status."""
    return {{"status": "ok", "plugin": "{name}"}}

# Add more routes here
'''

SCHEMAS_TEMPLATE = '''"""
Pydantic schemas for {name} plugin.
"""

from pydantic import BaseModel

class StatusResponse(BaseModel):
    """Plugin status response."""
    status: str
    plugin: str

# Add more schemas here
'''

UI_PACKAGE_JSON = """{{
    "name": "@dryade/{name}-ui",
    "version": "0.1.0",
    "private": true,
    "type": "module",
    "scripts": {{
        "dev": "vite",
        "build": "vite build",
        "preview": "vite preview"
    }},
    "dependencies": {{
        "react": "^18.2.0",
        "react-dom": "^18.2.0"
    }},
    "devDependencies": {{
        "@types/react": "^18.2.0",
        "@types/react-dom": "^18.2.0",
        "@vitejs/plugin-react": "^4.0.0",
        "typescript": "^5.0.0",
        "vite": "^5.0.0"
    }}
}}
"""

VITE_CONFIG_TEMPLATE = """import {{ defineConfig }} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({{
  plugins: [react()],
  build: {{
    lib: {{
      entry: 'src/main.tsx',
      name: '{class_name}PluginUI',
      fileName: () => 'bundle.js',
      formats: ['iife'],
    }},
    rollupOptions: {{
      external: [],
      output: {{
        inlineDynamicImports: true,
        assetFileNames: (assetInfo) => {{
          if (assetInfo.name?.endsWith('.css')) return 'styles.css';
          return assetInfo.name || 'asset';
        }},
      }},
    }},
    minify: 'terser',
    target: 'esnext',
    outDir: 'dist',
    cssCodeSplit: false,
  }},
  define: {{
    'process.env.NODE_ENV': '"production"',
  }},
}});
"""

TSCONFIG_TEMPLATE = """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
"""

UI_MAIN_TEMPLATE = """import React from 'react';
import ReactDOM from 'react-dom/client';

function App() {{
  return (
    <div style={{{{ padding: '1rem' }}}}>
      <h1>{name_title} Plugin</h1>
      <p>Plugin UI goes here</p>
    </div>
  );
}}

// Mount to root element provided by host iframe
const root = document.getElementById('root');
if (root) {{
  ReactDOM.createRoot(root).render(<App />);
}}
"""

def to_class_name(name: str) -> str:
    """Convert plugin name to class name."""
    return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))

@click.command("create-plugin")
@click.argument("name")
@click.option("--description", "-d", default="A Dryade plugin", help="Plugin description")
@click.option("--author", "-a", default="Community", help="Plugin author")
@click.option("--with-ui", is_flag=True, help="Include UI scaffold")
@click.option("--with-routes", is_flag=True, help="Include API routes")
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: plugins/)")
def create_plugin(
    name: str, description: str, author: str, with_ui: bool, with_routes: bool, output: str | None
):
    """
    Create a new Dryade plugin.

    NAME is the plugin name (lowercase, underscores allowed).

    Examples:
        dryade create-plugin my-plugin
        dryade create-plugin analyzer --with-ui --with-routes
        dryade create-plugin custom -o ./my-plugins
    """
    # Validate name
    if not name.replace("_", "").replace("-", "").isalnum():
        click.echo(click.style(f"Invalid plugin name: {name}", fg="red"))
        click.echo("Use only letters, numbers, underscores, and hyphens")
        return

    # Normalize name
    name = name.lower().replace("-", "_")
    class_name = to_class_name(name)

    # Determine output path
    if output:
        base_path = Path(output)
    else:
        base_path = Path("plugins")

    plugin_path = base_path / name

    # Check if exists
    if plugin_path.exists():
        click.echo(click.style(f"Plugin already exists: {plugin_path}", fg="red"))
        return

    click.echo(f"Creating plugin: {name}")
    click.echo(f"Location: {plugin_path}")
    click.echo("=" * 50)

    # Create directories
    plugin_path.mkdir(parents=True)
    click.echo(f"  Created: {plugin_path}/")

    # Create dryade.json
    api_paths = f'"/api/{name}"' if with_routes else ""
    manifest_content = MANIFEST_TEMPLATE.format(
        name=name,
        description=description,
        author=author,
        has_ui=str(with_ui).lower(),
        api_paths=api_paths,
    )
    (plugin_path / "dryade.json").write_text(manifest_content)
    click.echo("  Created: dryade.json")

    # Create plugin.py
    plugin_content = PLUGIN_TEMPLATE.format(
        name=name,
        description=description,
        class_name=class_name,
    )
    (plugin_path / "plugin.py").write_text(plugin_content)
    click.echo("  Created: plugin.py")

    # Create __init__.py
    init_content = (
        f'"""The {name} plugin."""\n\nfrom .plugin import plugin\n\n__all__ = ["plugin"]\n'
    )
    (plugin_path / "__init__.py").write_text(init_content)
    click.echo("  Created: __init__.py")

    # Create routes if requested
    if with_routes:
        routes_content = ROUTES_TEMPLATE.format(name=name)
        (plugin_path / "routes.py").write_text(routes_content)
        click.echo("  Created: routes.py")

        schemas_content = SCHEMAS_TEMPLATE.format(name=name)
        (plugin_path / "schemas.py").write_text(schemas_content)
        click.echo("  Created: schemas.py")

    # Track UI build result for next steps guidance
    ui_build_succeeded = False

    # Create UI if requested
    if with_ui:
        ui_path = plugin_path / "ui"
        ui_path.mkdir()
        (ui_path / "src").mkdir()

        (ui_path / "package.json").write_text(UI_PACKAGE_JSON.format(name=name))
        click.echo("  Created: ui/package.json")

        vite_config_content = VITE_CONFIG_TEMPLATE.format(class_name=class_name)
        (ui_path / "vite.config.ts").write_text(vite_config_content)
        click.echo("  Created: ui/vite.config.ts")

        (ui_path / "tsconfig.json").write_text(TSCONFIG_TEMPLATE)
        click.echo("  Created: ui/tsconfig.json")

        main_content = UI_MAIN_TEMPLATE.replace("{name_title}", class_name)
        (ui_path / "src" / "main.tsx").write_text(main_content)
        click.echo("  Created: ui/src/main.tsx")

        # Auto-build if npm is available
        if shutil.which("npm") is None:
            click.echo(
                click.style(
                    "  Warning: npm not found — skipping auto-build. Run 'dryade build-plugins' to build the UI bundle.",
                    fg="yellow",
                )
            )
        else:
            click.echo("\nInstalling UI dependencies...")
            install_result = subprocess.run(
                ["npm", "install"],
                cwd=ui_path,
                capture_output=True,
                text=True,
            )
            if install_result.returncode == 0:
                click.echo("Building UI bundle...")
                build_result = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=ui_path,
                    capture_output=True,
                    text=True,
                )
                if build_result.returncode == 0:
                    click.echo(click.style("  UI bundle built successfully!", fg="green"))
                    ui_build_succeeded = True
                else:
                    click.echo(
                        click.style(
                            "  Warning: UI build failed. Run 'dryade build-plugins' to retry.",
                            fg="yellow",
                        )
                    )
                    if build_result.stderr:
                        click.echo(build_result.stderr[:500])
            else:
                click.echo(
                    click.style(
                        "  Warning: npm install failed. Run 'dryade build-plugins' to retry.",
                        fg="yellow",
                    )
                )
                if install_result.stderr:
                    click.echo(install_result.stderr[:500])

    # Summary
    click.echo("\n" + "=" * 50)
    click.echo(click.style("Plugin created successfully!", fg="green", bold=True))
    click.echo("\nNext steps:")
    click.echo(f"  1. cd {plugin_path}")
    click.echo("  2. Edit plugin.py to add your logic")
    if with_routes:
        click.echo("  3. Add routes in routes.py")
    if with_ui:
        if ui_build_succeeded:
            click.echo("  3. dryade-pm push  (to hash, sign, and push to core)")
        else:
            click.echo("  3. dryade build-plugins  (build UI bundle)")
            click.echo("  4. dryade-pm push  (hash, sign, push to core)")
    click.echo(f"\nValidate with: dryade validate-plugin {plugin_path}")

if __name__ == "__main__":
    create_plugin()
