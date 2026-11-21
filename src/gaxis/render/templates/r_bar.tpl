stats <- summarise_groups(tidy)

p <- ggplot(stats, aes(x = x, y = mean, fill = hue)) +
  geom_col(position = DODGE, width = 0.75, colour = "black", linewidth = pt_to_lwd(0.4)) +
  geom_errorbar(
    aes(ymin = mean - err, ymax = mean + err),
    position = DODGE,
    width = 0.2,
    linewidth = pt_to_lwd(0.5)
  ) +
  scale_fill_manual(values = FILL_VALUES) +
  LABS +
  theme(legend.position = LEGEND_POSITION)

if (SPEC$annotate) {
  p <- p + geom_text(
    aes(label = formatC(mean, digits = 3, format = "g")),
    position = DODGE,
    vjust = -0.5,
    size = 0.8 * BASE_PT * 0.3528
  )
}

if (Sys.getenv("GAXIS_PANEL_SOURCE") != "1") save_all(p)
