edges <- data.frame(
  parent = as.character(raw[[SPEC$x]]),
  child = as.character(raw[[SPEC$y]]),
  stringsAsFactors = FALSE
)
if (!is.null(SPEC$weight)) {
  edges$length <- suppressWarnings(as.numeric(raw[[SPEC$weight]]))
  edges$length[is.na(edges$length) | edges$length < 0] <- 1
} else {
  edges$length <- 1
}
edges <- edges[
  !is.na(edges$parent) & !is.na(edges$child) & edges$parent != "" & edges$child != "",
  ,
  drop = FALSE
]
if (nrow(edges) == 0) stop("no branches to draw: check x/y/weight columns")
if (!("is_tip" %in% names(edges))) {
  edges$is_tip <- as.integer(!(edges$child %in% edges$parent))
}
if (!is.null(SPEC$hue)) edges$group <- as.character(raw[[SPEC$hue]]) else edges$group <- NA

kids <- split(edges$child, edges$parent)
branch <- setNames(edges$length, edges$child)
root <- setdiff(unique(edges$parent), unique(edges$child))[1]
if (is.na(root)) stop("tree has no root")

depth <- c()
ypos <- c()
tips <- c()
walk <- function(node, current) {
  depth[node] <<- current
  node_kids <- kids[[node]]
  if (is.null(node_kids) || length(node_kids) == 0) {
    tips[length(tips) + 1] <<- node
    ypos[node] <<- length(tips) - 1
  } else {
    for (kid in node_kids) walk(kid, current + branch[[kid]])
    ypos[node] <<- mean(ypos[node_kids])
  }
}
walk(root, 0)
span <- max(depth)
if (!is.finite(span) || span <= 0) span <- 1

x0 <- depth[edges$parent] / span
y0 <- ypos[edges$parent]
x1 <- depth[edges$child] / span
y1 <- ypos[edges$child]
horizontal <- data.frame(x = x0, y = y0, xend = x1, yend = y0)
vertical <- data.frame(x = x1, y = y0, xend = x1, yend = y1)
labels <- data.frame(
  x = x1 + if (is.null(SPEC$hue)) 0.015 else 0.035,
  y = y1,
  label = edges$child,
  group = edges$group,
  is_tip = edges$is_tip
)
labels <- labels[labels$is_tip == 1, , drop = FALSE]

p <- ggplot() +
  geom_segment(data = horizontal, aes(x = x, y = y, xend = xend, yend = yend),
               linewidth = pt_to_lwd(LINE_WIDTH), colour = "black") +
  geom_segment(data = vertical, aes(x = x, y = y, xend = xend, yend = yend),
               linewidth = pt_to_lwd(LINE_WIDTH), colour = "black") +
  geom_text(data = labels, aes(x = x, y = y, label = label),
            hjust = 0, size = BASE_PT / .pt, family = FONT_FAMILY) +
  { if (is.null(SPEC$hue)) NULL else
      list(
        geom_point(data = labels, aes(x = x - 0.02, y = y, colour = group),
                   shape = 15, size = 1.6),
        scale_colour_manual(values = COLORS, name = SPEC$hue),
        theme(legend.position = "right",
              legend.title = element_text(size = BASE_PT),
              legend.text = element_text(size = BASE_PT))
      ) } +
  coord_cartesian(xlim = c(0, 1.15), ylim = c(-0.8, nrow(labels) - 0.2), clip = "off") +
  theme_void(base_size = BASE_PT, base_family = FONT_FAMILY) +
  theme(plot.title = element_text(size = TITLE_PT, hjust = 0),
        plot.margin = margin(2, 2, 2, 2, unit = "mm"))
if (!is.null(SPEC$title)) p <- p + labs(title = SPEC$title)
save_all(p)
