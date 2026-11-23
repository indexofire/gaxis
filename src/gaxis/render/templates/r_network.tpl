edges <- data.frame(
  source = as.character(raw[[SPEC$x]]),
  target = as.character(raw[[SPEC$y]]),
  stringsAsFactors = FALSE
)
if (!is.null(SPEC$weight)) {
  edges$weight <- suppressWarnings(as.numeric(raw[[SPEC$weight]]))
  edges$weight[is.na(edges$weight) | edges$weight <= 0] <- 1
} else {
  edges$weight <- 1
}
edges <- edges[
  !is.na(edges$source) & !is.na(edges$target) &
    edges$source != "" & edges$target != "" & edges$source != edges$target,
  ,
  drop = FALSE
]
if (nrow(edges) == 0) stop("no edges to draw: check x/y/weight columns")
if ("source_class" %in% names(raw)) {
  edges$source_class <- as.character(raw[["source_class"]])
  edges$target_class <- as.character(raw[["target_class"]])
} else if (!is.null(SPEC$hue)) {
  edges$source_class <- as.character(raw[[SPEC$hue]])
  edges$target_class <- edges$source_class
} else {
  edges$source_class <- NA_character_
  edges$target_class <- NA_character_
}

nodes <- unique(c(edges$source, edges$target))
angles <- (seq(0, 2 * pi, length.out = length(nodes) + 1)[seq_along(nodes)] + pi / 2)
pos <- data.frame(
  node = nodes,
  x = cos(angles),
  y = sin(angles),
  stringsAsFactors = FALSE
)
edges <- merge(edges, pos, by.x = "source", by.y = "node", all.x = TRUE)
names(edges)[names(edges) == "x"] <- "x0"
names(edges)[names(edges) == "y"] <- "y0"
edges <- merge(edges, pos, by.x = "target", by.y = "node", all.x = TRUE)
names(edges)[names(edges) == "x"] <- "x1"
names(edges)[names(edges) == "y"] <- "y1"
edges$lineweight <- 0.3 + 1.2 * edges$weight / max(edges$weight)
edges$alpha <- 0.25 + 0.45 * edges$weight / max(edges$weight)
degree <- table(c(edges$source, edges$target))
pos$degree <- as.numeric(degree[pos$node])
pos$degree[is.na(pos$degree)] <- 0
pos$size <- 1.2 + 2.0 * pos$degree / max(1, max(pos$degree))
node_group <- data.frame(
  node = c(edges$source, edges$target),
  group = c(edges$source_class, edges$target_class),
  stringsAsFactors = FALSE
)
node_group <- node_group[!duplicated(node_group$node), , drop = FALSE]
pos <- merge(pos, node_group, by = "node", all.x = TRUE)
groups <- sort(unique(pos$group[!is.na(pos$group) & pos$group != ""]))
used_colors <- unique(unlist(SPEC$color_map))
fallback_colors <- setdiff(COLORS, used_colors)
if (length(fallback_colors) == 0) fallback_colors <- COLORS
group_colors <- c()
next_color <- 1
for (i in seq_along(groups)) {
  mapped <- SPEC$color_map[[groups[i]]]
  if (is.null(mapped)) {
    mapped <- fallback_colors[((next_color - 1) %% length(fallback_colors)) + 1]
    next_color <- next_color + 1
  }
  group_colors[[groups[i]]] <- mapped
}
pos$group <- factor(pos$group, levels = groups)

p <- ggplot() +
  geom_curve(
    data = edges,
    aes(x = x0, y = y0, xend = x1, yend = y1,
        linewidth = lineweight, alpha = alpha),
    curvature = 0.25,
    colour = COLORS[1],
    lineend = "round"
  ) +
  { if (length(groups) == 0) {
      geom_point(data = pos, aes(x = x, y = y, size = size),
                 colour = COLORS[1], fill = COLORS[1], shape = 21,
                 stroke = pt_to_lwd(0.4))
    } else {
      geom_point(data = pos, aes(x = x, y = y, size = size, fill = group),
                 shape = 21, colour = "white", stroke = pt_to_lwd(0.4))
    } } +
  { if (length(groups) == 0) NULL else
      scale_fill_manual(values = group_colors, name = "class") } +
  geom_text(
    data = pos,
    aes(x = x * 1.14, y = y * 1.14, label = node),
    hjust = ifelse(pos$x >= 0, 0, 1),
    size = BASE_PT / .pt,
    family = FONT_FAMILY
  ) +
  scale_linewidth_identity() +
  scale_alpha_identity() +
  scale_size_identity() +
  coord_equal(xlim = c(-1.4, 1.4), ylim = c(-1.4, 1.4), clip = "off") +
  theme_void(base_size = BASE_PT, base_family = FONT_FAMILY) +
  theme(plot.title = element_text(size = TITLE_PT, hjust = 0),
        plot.margin = margin(2, 2, 2, 2, unit = "mm"))
if (!is.null(SPEC$title)) p <- p + labs(title = SPEC$title)
save_all(p)
