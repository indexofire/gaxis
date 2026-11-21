rows = load_rows(DATA_PATH)
stats, levels, groups = summarise(rows, SPEC["x"], SPEC["y"], SPEC["hue"], SPEC["yerr"])
x_numeric = numeric_column(rows, SPEC["x"])

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
for index, group in enumerate(groups):
    subset = [s for s in stats if s["group"] == group]
    xs = [float(str(s["level"])) if x_numeric else str(s["level"]) for s in subset]
    ax.errorbar(
        xs,
        [float(s["mean"]) for s in subset],
        yerr=[float(s["err"]) for s in subset],
        label=None if group is None else str(group),
        color=COLORS[index % len(COLORS)],
        marker="o",
        markersize=float(matplotlib.rcParams["lines.markersize"]),
        linewidth=float(matplotlib.rcParams["lines.linewidth"]),
        elinewidth=0.5,
        capsize=1.5,
    )
if not x_numeric:
    ax.set_xticks(range(len(levels)), [str(level) for level in levels])

finish(ax)
