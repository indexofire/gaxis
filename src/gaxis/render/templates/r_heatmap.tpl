stats <- summarise_groups(tidy)
# Keep annotation text legible on both dark and light viridis cells.
midpoint <- stats::median(stats$mean, na.rm = TRUE)
stats$label_colour <- ifelse(stats$mean > midpoint, "black", "white")

p <- ggplot(stats, aes(x = x, y = hue, fill = mean)) +
  geom_tile(colour = "white", linewidth = pt_to_lwd(0.4)) +
  scale_fill_viridis_c() +
  labs(x = SPEC$xlabel, y = SPEC$hue, title = SPEC$title, fill = SPEC$ylabel) +
  theme(
    axis.line = element_blank(),
    axis.ticks = element_blank(),
    legend.position = "right"
  )

if (SPEC$annotate) {
  p <- p + geom_text(
    aes(label = formatC(mean, digits = 3, format = "g"), colour = label_colour),
    size = 0.8 * BASE_PT * 0.3528,
    show.legend = FALSE
  ) + scale_colour_identity()
}

if (Sys.getenv("GAXIS_PANEL_SOURCE") != "1") save_all(p)
