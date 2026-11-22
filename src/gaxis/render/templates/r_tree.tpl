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
labels <- data.frame(x = x1 + 0.015, y = y1, label = edges$child)

p <- ggplot() +
  geom_segment(data = horizontal, aes(x = x, y = y, xend = xend, yend = yend),
               linewidth = pt_to_lwd(LINE_WIDTH), colour = "black") +
  geom_segment(data = vertical, aes(x = x, y = y, xend = xend, yend = yend),
               linewidth = pt_to_lwd(LINE_WIDTH), colour = "black") +
  geom_text(data = labels, aes(x = x, y = y, label = label),
            hjust = 0, size = BASE_PT / .pt, family = FONT_FAMILY) +
  coord_cartesian(xlim = c(0, 1.15), ylim = c(-0.8, nrow(labels) - 0.2), clip = "off") +
  theme_void(base_size = BASE_PT, base_family = FONT_FAMILY) +
  theme(plot.title = element_text(size = TITLE_PT, hjust = 0),
        plot.margin = margin(2, 2, 2, 2, unit = "mm"))
if (!is.null(SPEC$title)) p <- p + labs(title = SPEC$title)
save_all(p)
