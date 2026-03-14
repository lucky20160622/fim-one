"""Compare two workflow blueprints and produce a human-readable change summary.

This module is a pure function with no database access — it takes two raw
blueprint dicts and returns a concise English description of what changed.
"""

from __future__ import annotations

from typing import Any


def _node_label(node: dict[str, Any]) -> str:
    """Derive a display label for a node.

    Preference order: data.label > data.type > node id.
    """
    data = node.get("data") or {}
    label = data.get("label") or data.get("type") or node.get("type") or node.get("id", "?")
    return str(label)


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    """Return a hashable identity tuple for an edge."""
    return (
        edge.get("source", ""),
        edge.get("target", ""),
        edge.get("sourceHandle"),
        edge.get("targetHandle"),
    )


def _nodes_by_id(blueprint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index nodes by their ``id`` field."""
    return {n["id"]: n for n in blueprint.get("nodes", []) if "id" in n}


def _config_changed(old_node: dict[str, Any], new_node: dict[str, Any]) -> bool:
    """Check whether two nodes differ in their ``data`` config (excluding position)."""
    old_data = old_node.get("data") or {}
    new_data = new_node.get("data") or {}
    return old_data != new_data


def _position_changed(old_node: dict[str, Any], new_node: dict[str, Any]) -> bool:
    """Check whether a node moved on the canvas."""
    old_pos = old_node.get("position") or {}
    new_pos = new_node.get("position") or {}
    return old_pos != new_pos


def compute_blueprint_diff(
    old_blueprint: dict[str, Any],
    new_blueprint: dict[str, Any],
) -> str:
    """Compare two workflow blueprints and return a human-readable summary.

    Parameters
    ----------
    old_blueprint:
        The previous version's blueprint dict (``{nodes, edges, viewport}``).
    new_blueprint:
        The new version's blueprint dict.

    Returns
    -------
    str
        A concise description such as:
        ``"Added 2 nodes (LLM, CodeExecution), removed 1 node (HTTPRequest),
        modified 3 nodes, added 1 edge, removed 2 edges"``

        Returns ``"No changes"`` when the blueprints are identical.
    """
    old_nodes = _nodes_by_id(old_blueprint)
    new_nodes = _nodes_by_id(new_blueprint)

    old_node_ids = set(old_nodes.keys())
    new_node_ids = set(new_nodes.keys())

    added_ids = new_node_ids - old_node_ids
    removed_ids = old_node_ids - new_node_ids
    common_ids = old_node_ids & new_node_ids

    # Categorise modified nodes
    config_modified_ids: list[str] = []
    position_only_ids: list[str] = []

    for nid in sorted(common_ids):
        old_n = old_nodes[nid]
        new_n = new_nodes[nid]
        cfg = _config_changed(old_n, new_n)
        pos = _position_changed(old_n, new_n)
        if cfg:
            config_modified_ids.append(nid)
        elif pos:
            position_only_ids.append(nid)

    # Edge diff — compare by (source, target, sourceHandle, targetHandle)
    old_edges = {_edge_key(e) for e in old_blueprint.get("edges", [])}
    new_edges = {_edge_key(e) for e in new_blueprint.get("edges", [])}

    added_edges = new_edges - old_edges
    removed_edges = old_edges - new_edges

    # Build summary parts
    parts: list[str] = []

    if added_ids:
        labels = ", ".join(_node_label(new_nodes[nid]) for nid in sorted(added_ids))
        count = len(added_ids)
        noun = "node" if count == 1 else "nodes"
        parts.append(f"Added {count} {noun} ({labels})")

    if removed_ids:
        labels = ", ".join(_node_label(old_nodes[nid]) for nid in sorted(removed_ids))
        count = len(removed_ids)
        noun = "node" if count == 1 else "nodes"
        parts.append(f"Removed {count} {noun} ({labels})")

    if config_modified_ids:
        labels = ", ".join(
            _node_label(new_nodes[nid]) for nid in config_modified_ids
        )
        count = len(config_modified_ids)
        noun = "node" if count == 1 else "nodes"
        parts.append(f"Modified {count} {noun} ({labels})")

    if position_only_ids:
        count = len(position_only_ids)
        noun = "node" if count == 1 else "nodes"
        parts.append(f"Repositioned {count} {noun}")

    if added_edges:
        count = len(added_edges)
        noun = "edge" if count == 1 else "edges"
        parts.append(f"Added {count} {noun}")

    if removed_edges:
        count = len(removed_edges)
        noun = "edge" if count == 1 else "edges"
        parts.append(f"Removed {count} {noun}")

    return ", ".join(parts) if parts else "No changes"
