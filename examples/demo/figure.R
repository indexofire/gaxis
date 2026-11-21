suppressPackageStartupMessages(library(ggplot2))
d <- data.frame(
  genotype = factor(c("WT", "dpsA", "rpoS", "hfq"), levels = c("WT", "dpsA", "rpoS", "hfq")),
  expr = c(120, 85, 150, 95)
)
p <- ggplot(d, aes(genotype, expr)) +
  geom_col(fill = "#009E73", colour = "black", linewidth = 0.3) +
  labs(x = "genotype", y = "expr fpkm") +
  theme_classic(base_size = 7)
ggsave("figure.png", p, width = 89, height = 60, units = "mm", dpi = 600,
       device = ragg::agg_png, bg = "white")
