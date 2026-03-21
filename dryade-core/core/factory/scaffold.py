"""Jinja2 template rendering and file writing for the Agent Factory."""

import logging
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from core.factory.models import ArtifactType

logger = logging.getLogger(__name__)

__all__ = [
    "scaffold_artifact",
    "get_template_dir",
    "get_output_dir",
    "list_available_frameworks",
    "TEMPLATE_DIR",
]

# ---------------------------------------------------------------------------
# Jinja2 Environment
# ---------------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=False,  # CRITICAL: generating Python code, NOT HTML
    keep_trailing_newline=True,  # Preserve file endings
    trim_blocks=True,  # Remove first newline after block tag
    lstrip_blocks=True,  # Strip leading whitespace before block tags
)

# ---------------------------------------------------------------------------
# Mapping from ArtifactType to template subdirectory name
# ---------------------------------------------------------------------------

_TYPE_TO_DIR = {
    ArtifactType.AGENT: "agents",
    ArtifactType.TOOL: "tools",
    ArtifactType.SKILL: "skills",
}

# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

def get_template_dir(artifact_type: ArtifactType, framework: str) -> Path:
    """Return the template subdirectory for an artifact type and framework.

    Args:
        artifact_type: The type of artifact (agent, tool, skill).
        framework: The framework identifier (e.g. 'crewai', 'mcp_server').

    Returns:
        Absolute path to the template subdirectory.

    Raises:
        ValueError: If artifact_type is not a recognized mapping.
    """
    if artifact_type not in _TYPE_TO_DIR:
        raise ValueError(
            f"Unknown artifact type: {artifact_type}. "
            f"Valid types: {sorted(t.value for t in _TYPE_TO_DIR)}"
        )
    return TEMPLATE_DIR / _TYPE_TO_DIR[artifact_type] / framework

def get_output_dir(artifact_type: ArtifactType, name: str, base_dir: str | None = None) -> Path:
    """Resolve the output directory for a scaffolded artifact.

    Args:
        artifact_type: The type of artifact.
        name: The artifact name (used as subdirectory).
        base_dir: Optional base directory override. If provided, the output
                  will be ``base_dir/name``. Otherwise defaults to
                  ``settings.agents_dir/name`` for agents, or
                  ``{type_plural}/name`` relative to the project root for others.

    Returns:
        Path to the output directory (may not exist yet).
    """
    if base_dir is not None:
        return Path(base_dir) / name

    # For agents, use the configured agents_dir (absolute path) so scaffolded
    # agents land in the same directory that auto-discovery scans at startup.
    if artifact_type == ArtifactType.AGENT:
        from core.config import get_settings

        return Path(get_settings().agents_dir) / name

    return Path(_TYPE_TO_DIR[artifact_type]) / name

# ---------------------------------------------------------------------------
# Framework discovery
# ---------------------------------------------------------------------------

def list_available_frameworks(artifact_type: ArtifactType) -> list[str]:
    """List framework IDs that have at least one .j2 template file.

    Args:
        artifact_type: The type of artifact to query.

    Returns:
        Sorted list of framework directory names containing .j2 files.
        Returns an empty list if the type directory does not exist.
    """
    if artifact_type not in _TYPE_TO_DIR:
        return []

    type_dir = TEMPLATE_DIR / _TYPE_TO_DIR[artifact_type]
    if not type_dir.is_dir():
        return []

    frameworks: list[str] = []
    for subdir in sorted(type_dir.iterdir()):
        if subdir.is_dir() and any(subdir.glob("*.j2")):
            frameworks.append(subdir.name)
    return frameworks

# ---------------------------------------------------------------------------
# Main scaffold function
# ---------------------------------------------------------------------------

def scaffold_artifact(
    config: dict,
    artifact_type: ArtifactType,
    framework: str,
    base_dir: str | None = None,
) -> tuple[bool, str, str]:
    """Render Jinja2 templates and write scaffolded files to disk.

    This is the core file-generation engine of the Agent Factory. It resolves
    template files for the given ``artifact_type``/``framework`` combination,
    renders each ``.j2`` template using the provided ``config`` dict as context,
    and writes the rendered files (with ``.j2`` stripped) into the output
    directory.

    Args:
        config: Template context dictionary (LLM-generated artifact config).
        artifact_type: Type of artifact to scaffold (agent/tool/skill).
        framework: Framework identifier (e.g. 'crewai', 'langchain').
        base_dir: Optional base directory for output. Defaults to
                  ``{type_plural}/{name}`` relative to the working directory.

    Returns:
        A 3-tuple ``(success, output_path, message)`` where *success* is
        ``True`` if all templates rendered and wrote successfully, *output_path*
        is the string path to the generated directory (empty on failure), and
        *message* is a human-readable status string.
    """
    artifact_name = config.get("name", "unnamed")

    # 1. Resolve template subdirectory
    try:
        tmpl_dir = get_template_dir(artifact_type, framework)
    except ValueError as exc:
        logger.warning("Scaffold failed: %s", exc)
        return (False, "", str(exc))

    if not tmpl_dir.is_dir():
        msg = f"No templates for {artifact_type.value}/{framework}"
        logger.warning("Scaffold failed: %s", msg)
        return (False, "", msg)

    # 2. Discover .j2 template files
    j2_files = sorted(tmpl_dir.glob("*.j2"))
    if not j2_files:
        msg = f"No templates found in {artifact_type.value}/{framework}"
        logger.warning("Scaffold failed: %s", msg)
        return (False, "", msg)

    # 3. Resolve output directory
    output_dir = get_output_dir(artifact_type, artifact_name, base_dir)

    if output_dir.exists():
        msg = f"Directory already exists: {output_dir}. Use update, not create."
        logger.warning("Scaffold failed: %s", msg)
        return (False, "", msg)

    # 4. Create output directory
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        msg = f"Directory already exists: {output_dir}. Use update, not create."
        logger.warning("Scaffold failed: %s", msg)
        return (False, "", msg)

    # 4b. Normalize tools and capabilities for templates.
    # LLM config generators may produce these in varying formats:
    #   tools: flat strings ["web_search"] or dicts [{"name": "web_search", ...}]
    #   capabilities: flat strings ["pep8_checker"] or dicts [{"name": "pep8_checker", ...}]
    # Templates expect:
    #   tools: objects with .tool, .server, .description
    #   capabilities: flat strings
    raw_tools = config.get("tools", [])
    raw_servers = config.get("mcp_servers", [])
    if raw_tools:
        structured_tools = []
        for i, tool_item in enumerate(raw_tools):
            if isinstance(tool_item, str):
                tool_name = tool_item
                desc = tool_name.replace("_", " ").replace("-", " ").title()
            elif isinstance(tool_item, dict):
                tool_name = tool_item.get("name", tool_item.get("tool", ""))
                desc = tool_item.get("description", tool_name.replace("_", " ").title())
            else:
                continue
            server_item = (
                raw_servers[i]
                if i < len(raw_servers)
                else (raw_servers[0] if raw_servers else "unknown")
            )
            server_name = (
                server_item.get("name", server_item.get("host", "unknown"))
                if isinstance(server_item, dict)
                else server_item
            )
            structured_tools.append({"tool": tool_name, "server": server_name, "description": desc})
        config = {**config, "tools": structured_tools}

    # Normalize capabilities to flat strings
    raw_caps = config.get("capabilities", [])
    if raw_caps and isinstance(raw_caps[0], dict):
        config = {
            **config,
            "capabilities": [c.get("name", c.get("description", str(c))) for c in raw_caps],
        }

    # 5. Render templates
    rendered_files: list[str] = []
    try:
        for j2_file in j2_files:
            # Template path relative to TEMPLATE_DIR (forward slashes)
            rel_template = j2_file.relative_to(TEMPLATE_DIR).as_posix()
            template = _env.get_template(rel_template)
            rendered = template.render(**config)

            # Output file name: strip .j2 extension
            out_name = j2_file.stem  # e.g. "crew.py" from "crew.py.j2"
            out_path = output_dir / out_name
            out_path.write_text(rendered, encoding="utf-8")
            rendered_files.append(out_name)

    except TemplateNotFound as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        msg = f"Template not found: {exc}"
        logger.warning("Scaffold failed: %s", msg)
        return (False, "", msg)

    except Exception as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        msg = f"Template render error: {exc}"
        logger.warning("Scaffold failed: %s", msg)
        return (False, "", msg)

    # 6. Success
    msg = f"Scaffolded {artifact_name} ({len(rendered_files)} files) at {output_dir}"
    logger.info(msg)
    return (True, str(output_dir), msg)
