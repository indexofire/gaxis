plot_data <- tidy[!is.na(tidy$y), ]
plot_data$x_num <- if (x_is_numeric) as.numeric(as.character(plot_data$x)) else plot_data$x

p <- ggplot(plot_data, aes(x = x_num, y = y, colour = hue)) +
  geom_point(size = MARKER_SIZE * 0.3528, alpha = 0.9, stroke = pt_to_lwd(0.6)) +
  scale_colour_manual(values = FILL_VALUES) +
  LABS_COLOUR +
  theme(legend.position = LEGEND_POSITION)

if (Sys.getenv("GAXIS_PANEL_SOURCE") != "1") save_all(p)
