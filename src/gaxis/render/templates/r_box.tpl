if (is.null(SPEC$y)) stop("box plots require a numeric y column")

plot_data <- tidy[!is.na(tidy$y), ]

p <- ggplot(plot_data, aes(x = x, y = y, fill = hue)) +
  geom_boxplot(
    position = DODGE,
    width = 0.7,
    outlier.shape = NA,
    linewidth = pt_to_lwd(0.4)
  ) +
  scale_fill_manual(values = FILL_VALUES) +
  LABS +
  theme(legend.position = LEGEND_POSITION)

if (Sys.getenv("GAXIS_PANEL_SOURCE") != "1") save_all(p)
