rows = load_rows(DATA_PATH)
groups = categories(rows, SPEC["hue"]) if SPEC["hue"] else [None]

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
for index, group in enumerate(groups):
    subset = [
        r
        for r in rows
        if (group is None or r[SPEC["hue"]] == group)
        and r[SPEC["x"]] not in MISSING
        and r[SPEC["y"]] not in MISSING
    ]
    ax.scatter(
        [float(r[SPEC["x"]]) for r in subset],
        [float(r[SPEC["y"]]) for r in subset],
        s=3.0 * float(matplotlib.rcParams["lines.markersize"]),
        label=None if group is None else str(group),
        color=COLORS[index % len(COLORS)],
        edgecolor="black",
        linewidth=0.3,
        alpha=0.9,
        zorder=3,
    )

finish(ax)
