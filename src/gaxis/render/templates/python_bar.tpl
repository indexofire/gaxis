rows = load_rows(DATA_PATH)
stats, levels, groups = summarise(rows, SPEC["x"], SPEC["y"], SPEC["hue"], SPEC["yerr"])

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
bar_width = 0.8 / len(groups)
centres = {level: index for index, level in enumerate(levels)}


def x_position(level: str, group_index: int) -> float:
    """Cluster the groups side by side inside each x level."""
    return centres[level] + (group_index - (len(groups) - 1) / 2) * bar_width


for index, group in enumerate(groups):
    subset = [s for s in stats if s["group"] == group]
    ax.bar(
        [x_position(s["level"], index) for s in subset],
        [float(s["mean"]) for s in subset],
        width=bar_width * 0.88,
        yerr=[float(s["err"]) for s in subset],
        label=None if group is None else str(group),
        color=COLORS[index % len(COLORS)],
        edgecolor="black",
        linewidth=0.4,
        error_kw={"elinewidth": 0.5, "capsize": 1.5},
    )

ax.set_xticks(range(len(levels)), [str(level) for level in levels])
if SPEC["annotate"]:
    for s in stats:
        ax.annotate(
            f"{float(s['mean']):.3g}",
            (x_position(str(s["level"]), groups.index(s["group"])), float(s["mean"])),
            ha="center",
            va="bottom",
            fontsize=0.85 * float(matplotlib.rcParams["font.size"]),
        )

finish(ax)
