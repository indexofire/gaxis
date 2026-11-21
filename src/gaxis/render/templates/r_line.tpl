stats <- summarise_groups(tidy)
stats$x_num <- if (x_is_numeric) as.numeric(as.character(stats$x)) else stats$x

p <- ggplot(stats, aes(x = x_num, y = mean, colour = hue, group = hue)) +
  geom_line(linewidth = pt_to_lwd(LINE_WIDTH)) +
  geom_point(size = MARKER_SIZE * 0.3528) +
  geom_errorbar(
    aes(ymin = mean - err, ymax = mean + err),
    width = 0.2,
    linewidth = pt_to_lwd(0.5)
  ) +
  scale_colour_manual(values = FILL_VALUES) +
  LABS_COLOUR +
  theme(legend.position = LEGEND_POSITION)

if (Sys.getenv("GAXIS_PANEL_SOURCE") != "1") save_all(p)
