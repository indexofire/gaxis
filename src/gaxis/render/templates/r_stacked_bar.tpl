stats <- summarise_groups(tidy)

p <- ggplot(stats, aes(x = x, y = mean, fill = hue)) +
  geom_col(position = "stack", width = 0.75, colour = "black", linewidth = pt_to_lwd(0.4)) +
  scale_fill_manual(values = FILL_VALUES) +
  LABS +
  theme(legend.position = LEGEND_POSITION)

if (Sys.getenv("GAXIS_PANEL_SOURCE") != "1") save_all(p)
