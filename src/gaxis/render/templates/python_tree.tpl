rows = load_rows(DATA_PATH)
edges = []
children = {}
nodes = []
for row in rows:
    parent = row.get(SPEC["x"], "")
    child = row.get(SPEC["y"], "")
    if parent in MISSING or child in MISSING:
        continue
    raw_length = row.get(SPEC["weight"], "") if SPEC["weight"] else "1"
    try:
        length = float(raw_length) if raw_length not in MISSING else 1.0
    except ValueError:
        length = 1.0
    edges.append((parent, child, max(length, 0.0)))
    children.setdefault(parent, []).append(child)
    for node in (parent, child):
        if node not in nodes:
            nodes.append(node)

if not edges:
    raise SystemExit("no branches to draw: check x/y/weight columns")

child_set = {child for _parent, child, _length in edges}
roots = [node for node in children if node not in child_set]
if not roots:
    raise SystemExit("tree has no root")
root = roots[0]

depth = {}
branch = {child: length for _parent, child, length in edges}
order = []


def walk(node, current):
    depth[node] = current
    kids = children.get(node, [])
    if not kids:
        order.append(node)
    for kid in kids:
        walk(kid, current + branch.get(kid, 1.0))


walk(root, 0.0)
span = max(depth.values()) or 1.0
positions = {}
for index, tip in enumerate(order):
    positions[tip] = float(index)


def place(node):
    kids = children.get(node, [])
    if not kids:
        return positions[node]
    values = [place(kid) for kid in kids]
    positions[node] = sum(values) / len(values)
    return positions[node]


place(root)

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
line_width = float(matplotlib.rcParams["lines.linewidth"])
for parent, child, _length in edges:
    x0 = depth[parent] / span
    x1 = depth[child] / span
    y0 = positions[parent]
    y1 = positions[child]
    ax.plot([x0, x1], [y0, y0], color="black", linewidth=line_width)
    ax.plot([x1, x1], [y0, y1], color="black", linewidth=line_width)

offset = 0.015
for tip in order:
    ax.text(
        depth[tip] / span + offset,
        positions[tip],
        tip,
        ha="left",
        va="center",
        fontsize=float(matplotlib.rcParams["font.size"]) * 0.9,
    )
ax.set_xlim(0, 1.15)
ax.set_ylim(-0.8, len(order) - 0.2)
ax.axis("off")
matplotlib.rcParams["savefig.bbox"] = None
finish(ax)
