"""One-shot atlas scan of adauto — run with python atlas_scan.py"""
from atlas.mcp.server import _headless_pipeline
from pathlib import Path

report, outputs = _headless_pipeline(Path('.'))
graph = report.graph

print(f"Nodes: {graph.node_count}  Edges: {graph.edge_count}  Health: {report.system_health:.1f}  Insights: {len(report.insights)}")
print()

# Top complexity nodes
nodes = list(graph.nodes.values())
scored = []
for n in nodes:
    sig = n.signals or {}
    score = sig.get('complexity', 0) + sig.get('coupling', 0) * 2 + sig.get('churn', 0)
    scored.append((score, n))
scored.sort(reverse=True, key=lambda x: x[0])

print("=== TOP COMPLEXITY NODES ===")
for score, n in scored[:12]:
    kind = getattr(n.kind, 'value', str(n.kind))
    sigs = {k: round(v, 2) for k, v in list((n.signals or {}).items())[:3]}
    print(f"  {n.name:40s} {kind:12s} {sigs}")

print()
print("=== MODULE BREAKDOWN (nodes per file) ===")
base = str(Path('.').resolve())
by_file = {}
for n in nodes:
    raw = str(n.path)
    f = raw.replace(base, '').lstrip('/').lstrip('\\').replace('\\', '/')
    by_file[f] = by_file.get(f, 0) + 1
for f, cnt in sorted(by_file.items(), key=lambda x: -x[1])[:15]:
    print(f"  {cnt:3d}  {f}")

print()
print("=== INSIGHTS (first 12) ===")
for ins in list(report.insights)[:12]:
    sev = getattr(ins, 'severity', '')
    sev_val = getattr(sev, 'value', str(sev))
    # Try different attribute names
    msg = getattr(ins, 'message', None) or getattr(ins, 'description', None) or getattr(ins, 'text', None) or str(ins)
    print(f"  [{sev_val}] {msg[:100]}")

print()
print("=== EDGES (call relationships, first 20) ===")
for e in list(graph.edges)[:20]:
    kind = getattr(e.kind, 'value', str(e.kind))
    src_node = graph.nodes.get(e.source)
    tgt_node = graph.nodes.get(e.target)
    src = src_node.name if src_node else e.source[:20]
    tgt = tgt_node.name if tgt_node else e.target[:20]
    print(f"  {src:30s} --{kind}--> {tgt}")
