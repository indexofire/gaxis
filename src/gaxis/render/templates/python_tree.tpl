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

annotation_columns = []
for column in ([SPEC["hue"]] if SPEC["hue"] else []) + list(SPEC.get("annotations", [])):
    if column and column not in annotation_columns:
        annotation_columns.append(column)

tip_annotations = {tip: {} for tip in order}
for row in rows:
    child = row.get(SPEC["y"], "")
    if child not in positions:
        continue
    for column in annotation_columns:
        value = row.get(column, "")
        if value not in MISSING:
            tip_annotations[child][column] = value

keys = sorted(
    {
        f"{column}: {value}"
        for column in annotation_columns
        for value in {tip_annotations[tip].get(column, "") for tip in order}
        if value
    }
)
color_map = SPEC.get("color_map", {})
used = set(color_map.values())
fallback = [color for color in COLORS if color not in used] or list(COLORS)
key_color = {}
next_index = 0
for key in keys:
    value = key.split(": ", 1)[-1]
    mapped = color_map.get(value)
    if mapped:
        key_color[key] = mapped
    else:
        key_color[key] = fallback[next_index % len(fallback)]
        next_index += 1

offset = 0.015
strip_width = 0.03
for tip in order:
    x = depth[tip] / span
    y = positions[tip]
    for index, column in enumerate(annotation_columns):
        value = tip_annotations[tip].get(column, "")
        if value:
            ax.scatter(
                [x + offset + index * strip_width],
                [y],
                marker="s",
                s=18,
                color=key_color[f"{column}: {value}"],
                zorder=3,
            )
    label_x = x + offset + len(annotation_columns) * strip_width + 0.01
    ax.text(
        label_x,
        y,
        tip,
        ha="left",
        va="center",
        fontsize=float(matplotlib.rcParams["font.size"]) * 0.9,
    )

if keys:
    from matplotlib.patches import Patch

    ax.legend(
        handles=[Patch(facecolor=key_color[key], label=key) for key in keys],
        title="annotation",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0.0,
        frameon=False,
        fontsize=float(matplotlib.rcParams["font.size"]) * 0.8,
        title_fontsize=float(matplotlib.rcParams["font.size"]) * 0.8,
    )

ax.set_xlim(0, 1.15)
ax.set_ylim(-0.8, len(order) - 0.2)
ax.axis("off")
matplotlib.rcParams["savefig.bbox"] = None
finish(ax)
