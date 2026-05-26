#!/usr/bin/env python3
"""Rebuild graphify-out/wiki/ from graph.json + labels.json without invoking an LLM.

Wraps graphify.wiki.to_wiki() so the wiki/ export step doesn't require an LLM API key.
The caller is expected to have already curated labels (see scripts/label_coverage.py
or have a human/agent fill in placeholders) so that every community has a meaningful
label — otherwise placeholder filenames like Community_NN.md will surface in the
output.

Usage:
    python rebuild_wiki.py <project-path>

The project path must contain graphify-out/{graph.json,.graphify_labels.json}.
Output goes to graphify-out/wiki/ (graphify CLI's --wiki destination).

Exit codes:
    0 — wrote wiki successfully, zero placeholder files
    1 — wrote wiki but placeholder files remain (label coverage incomplete)
    2 — missing inputs or import failure
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def load_graph(graph_path: Path):
    """Build a networkx graph from graphify's graph.json."""
    import networkx as nx

    data = json.loads(graph_path.read_text())
    directed = data.get("directed", True)
    G = nx.DiGraph() if directed else nx.Graph()

    for node in data["nodes"]:
        nid = node["id"]
        attrs = {k: v for k, v in node.items() if k != "id"}
        G.add_node(nid, **attrs)

    for edge in data.get("links", data.get("edges", [])):
        src = edge.get("source")
        dst = edge.get("target")
        if src in G and dst in G:
            attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
            G.add_edge(src, dst, **attrs)

    return G, data


def build_communities(G):
    """Group node ids by their community attribute (set by graphify clustering)."""
    communities: dict[int, list[str]] = defaultdict(list)
    for nid, attrs in G.nodes(data=True):
        cid = attrs.get("community")
        if cid is not None:
            communities[int(cid)].append(nid)
    return dict(communities)


def main(project_path: str) -> int:
    project = Path(project_path).expanduser().resolve()
    graphify_out = project / "graphify-out"
    graph_path = graphify_out / "graph.json"
    labels_path = graphify_out / ".graphify_labels.json"
    wiki_out = graphify_out / "wiki"

    if not graph_path.exists():
        print(f"error: {graph_path} not found", file=sys.stderr)
        return 2
    if not labels_path.exists():
        print(f"error: {labels_path} not found", file=sys.stderr)
        return 2

    try:
        from graphify.wiki import to_wiki
    except ImportError as e:
        print(f"error: cannot import graphify.wiki — {e}", file=sys.stderr)
        return 2

    G, _ = load_graph(graph_path)
    communities = build_communities(G)
    raw_labels = json.loads(labels_path.read_text())
    community_labels = {int(k): v for k, v in raw_labels.items()}

    count = to_wiki(
        G=G,
        communities=communities,
        output_dir=str(wiki_out),
        community_labels=community_labels,
    )

    placeholder_re = re.compile(r"^(Community|Cluster)_\d+\.md$")
    placeholders = [p.name for p in wiki_out.glob("*.md") if placeholder_re.match(p.name)]

    print(f"wrote {count} articles + index.md to {wiki_out}")
    print(f"  nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}, communities: {len(communities)}")

    if placeholders:
        print(f"  WARNING: {len(placeholders)} placeholder files remain — label coverage incomplete", file=sys.stderr)
        for name in placeholders[:5]:
            print(f"    {name}", file=sys.stderr)
        if len(placeholders) > 5:
            print(f"    ... and {len(placeholders) - 5} more", file=sys.stderr)
        return 1

    print("  label coverage: 100%")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__.splitlines()[0], file=sys.stderr)
        print(f"usage: {sys.argv[0]} <project-path>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
