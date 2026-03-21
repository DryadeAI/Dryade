# Migrated from plugins/starter/reactflow/converter.py into core (Phase 222).

"""Export CrewAI Flows to ReactFlow JSON format for visualization.

This is the ONLY flow-related code we write.
Everything else uses native CrewAI Flows.

Target: ~100 LOC
"""

import json
import logging
from typing import Any

from crewai.flow.flow import Flow
from crewai.flow.flow_wrappers import ListenMethod, RouterMethod, StartMethod

logger = logging.getLogger("dryade.reactflow")

def flow_to_reactflow(flow_class: type[Flow]) -> dict[str, Any]:
    """Convert a CrewAI Flow class to ReactFlow JSON.

    Analyzes @start, @listen, @router decorators to build graph.

    Args:
        flow_class: A CrewAI Flow class

    Returns:
        ReactFlow-compatible JSON structure
    """
    logger.info(f"[REACTFLOW] Converting flow class '{flow_class.__name__}' to ReactFlow JSON")

    nodes = []
    edges = []

    # Analyze flow methods by checking wrapper types
    methods = {}
    logger.debug("[REACTFLOW] Analyzing flow methods")
    for name in dir(flow_class):
        # Skip private methods
        if name.startswith("_"):
            continue

        attr = getattr(flow_class, name)

        if isinstance(attr, StartMethod):
            methods[name] = {"type": "start", "method": attr}
            logger.debug(f"[REACTFLOW]   Found start method: {name}")
        elif isinstance(attr, ListenMethod):
            # Extract trigger methods from the wrapper (CrewAI uses __trigger_methods__)
            listen_to = getattr(attr, "__trigger_methods__", [])
            methods[name] = {
                "type": "listen",
                "listens_to": listen_to,
                "method": attr,
            }
            logger.debug(f"[REACTFLOW]   Found listen method: {name} (listens to: {listen_to})")
        elif isinstance(attr, RouterMethod):
            # Routers also have trigger methods
            listen_to = getattr(attr, "__trigger_methods__", [])
            methods[name] = {"type": "router", "listens_to": listen_to, "method": attr}
            logger.debug(f"[REACTFLOW]   Found router method: {name} (listens to: {listen_to})")

    logger.info(f"[REACTFLOW] Found {len(methods)} flow methods")

    # Build nodes with layout
    logger.debug("[REACTFLOW] Building nodes with layout")
    y_offset = 0
    x_center = 250
    node_positions = {}

    for name, info in methods.items():
        node_type = info["type"]

        # Style based on type
        style = get_node_style(node_type)

        node = {
            "id": name,
            "type": "default",
            "position": {"x": x_center, "y": y_offset},
            "data": {
                "label": name.replace("_", " ").title(),
                "nodeType": node_type,
            },
            "style": style,
        }
        nodes.append(node)
        node_positions[name] = y_offset
        y_offset += 120

    logger.info(f"[REACTFLOW] Created {len(nodes)} nodes")

    # Build edges (both listen and router methods have incoming edges)
    logger.debug("[REACTFLOW] Building edges")
    edge_id = 0
    for name, info in methods.items():
        if info["type"] in ("listen", "router"):
            listen_to = info.get("listens_to", [])
            if not isinstance(listen_to, (list, tuple)):
                listen_to = [listen_to]

            for source in listen_to:
                source_name = source if isinstance(source, str) else source.__name__
                edges.append(
                    {
                        "id": f"e{edge_id}",
                        "source": source_name,
                        "target": name,
                        "animated": True,
                        "style": {"stroke": "#888"},
                    }
                )
                logger.debug(f"[REACTFLOW]   Added edge: {source_name} -> {name}")
                edge_id += 1

    logger.info(f"[REACTFLOW] Created {len(edges)} edges")

    result = {
        "nodes": nodes,
        "edges": edges,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }

    logger.info(f"[REACTFLOW] ReactFlow JSON generated successfully for '{flow_class.__name__}'")
    logger.debug(f"[REACTFLOW] JSON size: {len(json.dumps(result))} bytes")

    return result

def get_node_style(node_type: str) -> dict[str, Any]:
    """Get style for a node based on its type."""
    styles = {
        "start": {
            "background": "#4CAF50",
            "color": "white",
            "border": "2px solid #2E7D32",
            "borderRadius": "8px",
        },
        "router": {
            "background": "#FF9800",
            "color": "white",
            "border": "2px solid #F57C00",
            "borderRadius": "50%",
        },
        "listen": {
            "background": "#2196F3",
            "color": "white",
            "border": "2px solid #1565C0",
            "borderRadius": "4px",
        },
    }
    return styles.get(node_type, styles["listen"])

def export_flow_json(flow_class: type[Flow], path: str) -> str:
    """Export flow to JSON file.

    Args:
        flow_class: A CrewAI Flow class
        path: Output file path

    Returns:
        Path to exported file
    """
    data = flow_to_reactflow(flow_class)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path

def get_flow_info(flow_class: type[Flow]) -> dict[str, Any]:
    """Get metadata about a flow.

    Args:
        flow_class: A CrewAI Flow class

    Returns:
        Flow metadata
    """
    graph = flow_to_reactflow(flow_class)
    nodes = [n["id"] for n in graph["nodes"]]
    entry_point = next(
        (n["id"] for n in graph["nodes"] if n["data"].get("nodeType") == "start"),
        nodes[0] if nodes else None,
    )

    return {
        "name": flow_class.__name__,
        "description": flow_class.__doc__ or "",
        "nodes": nodes,
        "entry_point": entry_point,
        "node_count": len(nodes),
        "edge_count": len(graph["edges"]),
    }
