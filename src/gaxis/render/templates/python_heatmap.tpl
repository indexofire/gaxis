rows = load_rows(DATA_PATH)
stats, levels, groups = summarise(rows, SPEC["x"], SPEC["y"], SPEC["hue"], SPEC["yerr"])
group_labels = [str(g) if g is not None else "value" for g in groups]

matrix = np.full((len(groups), len(levels)), np.nan)
for s in stats:
    matrix[groups.index(s["group"]), levels.index(s["level"])] = float(s["mean"])

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
image = ax.imshow(matrix, cmap="viridis", aspect="auto", interpolation="nearest")
colorbar = fig.colorbar(image, ax=ax, fraction=0.05, pad=0.02)
colorbar.set_label(SPEC["ylabel"] or "")
ax.set_xticks(range(len(levels)), [str(level) for level in levels])
ax.set_yticks(range(len(group_labels)), group_labels)
if SPEC["annotate"]:
    finite = matrix[np.isfinite(matrix)]
    midpoint = float(np.median(finite)) if finite.size else 0.0
    for row_index in range(len(groups)):
        for column_index in range(len(levels)):
            value = matrix[row_index, column_index]
            if not np.isnan(value):
                ax.annotate(
                    f"{value:.3g}",
                    (column_index, row_index),
                    ha="center",
                    va="center",
                    color="black" if value > midpoint else "white",
                    fontsize=0.85 * float(matplotlib.rcParams["font.size"]),
                )

finish(ax, ylabel=SPEC["hue"] or "", xlabel=SPEC["xlabel"])
