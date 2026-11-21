rows = load_rows(DATA_PATH)
stats, levels, groups = summarise(rows, SPEC["x"], SPEC["y"], SPEC["hue"], SPEC["yerr"])

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
bottom = np.zeros(len(levels))
for index, group in enumerate(groups):
    subset = [s for s in stats if s["group"] == group]
    heights = np.zeros(len(levels))
    for s in subset:
        heights[levels.index(s["level"])] = float(s["mean"])
    ax.bar(
        range(len(levels)),
        heights,
        bottom=bottom,
        width=0.72,
        label=None if group is None else str(group),
        color=COLORS[index % len(COLORS)],
        edgecolor="black",
        linewidth=0.4,
    )
    bottom += heights

ax.set_xticks(range(len(levels)), [str(level) for level in levels])
if SPEC["annotate"]:
    for position, total in enumerate(bottom):
        ax.annotate(
            f"{total:.3g}",
            (position, total),
            ha="center",
            va="bottom",
            fontsize=0.85 * float(matplotlib.rcParams["font.size"]),
        )

finish(ax)
