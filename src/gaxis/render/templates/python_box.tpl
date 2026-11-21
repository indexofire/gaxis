rows = load_rows(DATA_PATH)
levels = categories(rows, SPEC["x"])
groups = categories(rows, SPEC["hue"]) if SPEC["hue"] else [None]
box_width = 0.7 / len(groups)

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
for index, group in enumerate(groups):
    data = []
    positions = []
    for position, level in enumerate(levels):
        subset = [
            float(r[SPEC["y"]])
            for r in rows
            if r[SPEC["x"]] == level
            and (group is None or r[SPEC["hue"]] == group)
            and r[SPEC["y"]] not in MISSING
        ]
        if subset:
            data.append(subset)
            positions.append(position + (index - (len(groups) - 1) / 2) * box_width)
    if not data:
        continue
    artists = ax.boxplot(
        data,
        positions=positions,
        widths=box_width * 0.85,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 0.6},
        boxprops={"edgecolor": "black", "linewidth": 0.5},
        whiskerprops={"color": "black", "linewidth": 0.5},
        capprops={"color": "black", "linewidth": 0.5},
        label=None if group is None else str(group),
    )
    for patch in artists["boxes"]:
        patch.set_facecolor(COLORS[index % len(COLORS)])

ax.set_xticks(range(len(levels)), [str(level) for level in levels])
if SPEC["hue"]:
    ax.legend(title=SPEC["hue"], loc="best")

finish(ax)
