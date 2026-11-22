from matplotlib.patches import PathPatch
from matplotlib.path import Path

rows = load_rows(DATA_PATH)
edges = []
order = []
for row in rows:
    source = row.get(SPEC["x"], "")
    target = row.get(SPEC["y"], "")
    if source in MISSING or target in MISSING or source == target:
        continue
    raw_weight = row.get(SPEC["weight"], "") if SPEC["weight"] else "1"
    try:
        weight = float(raw_weight) if raw_weight not in MISSING else 1.0
    except ValueError:
        weight = 1.0
    edges.append((source, target, max(weight, 1e-9)))
    for node in (source, target):
        if node not in order:
            order.append(node)

if not edges:
    raise SystemExit("no edges to draw: check x/y/weight columns")

positions = {
    node: (np.cos(angle), np.sin(angle))
    for node, angle in zip(
        order,
        np.linspace(0, 2 * np.pi, len(order), endpoint=False) + np.pi / 2,
    )
}
degree = {node: 0 for node in order}
for source, target, _weight in edges:
    degree[source] += 1
    degree[target] += 1

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
max_weight = max(weight for _s, _t, weight in edges)
for source, target, weight in edges:
    x0, y0 = positions[source]
    x1, y1 = positions[target]
    control = (0.0, 0.0) if (x0 * x1 + y0 * y1) < 0 else ((x0 + x1) / 2, (y0 + y1) / 2)
    path = Path(
        [(x0, y0), control, (x1, y1)],
        [matplotlib.path.Path.MOVETO, matplotlib.path.Path.CURVE3, matplotlib.path.Path.CURVE3],
    )
    ax.add_patch(
        PathPatch(
            path,
            facecolor="none",
            edgecolor=COLORS[0],
            alpha=0.20 + 0.45 * (weight / max_weight),
            linewidth=float(matplotlib.rcParams["lines.linewidth"])
            * (0.35 + 1.65 * weight / max_weight),
        )
    )

max_degree = max(degree.values()) or 1
sizes = [30 + 90 * degree[node] / max_degree for node in order]
ax.scatter(
    [positions[node][0] for node in order],
    [positions[node][1] for node in order],
    s=sizes,
    color=COLORS[0],
    edgecolors="white",
    linewidths=0.4,
    zorder=3,
)
for node in order:
    x, y = positions[node]
    ax.annotate(
        node,
        (x, y),
        xytext=(1.06 * x, 1.06 * y),
        ha="left" if x >= 0 else "right",
        va="center",
        fontsize=float(matplotlib.rcParams["font.size"]) * 0.85,
    )
ax.set_aspect("equal")
ax.axis("off")
# Keep the journal page size: a circular layout has empty corners, so the
# globally-tight bbox would silently shrink the delivered PDF.
matplotlib.rcParams["savefig.bbox"] = None
finish(ax)
