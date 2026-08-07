options(stringsAsFactors = FALSE)

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for plotting")
}

library(ggplot2)

table_dir <- "results/tables"
figure_dir <- "results/figures/reproduced"
dir.create(figure_dir, recursive = TRUE, showWarnings = FALSE)

read_result <- function(filename, required) {
  path <- file.path(table_dir, filename)
  if (!file.exists(path)) stop("Missing analysis table: ", path)
  data <- read.csv(path, fileEncoding = "UTF-8", check.names = FALSE)
  missing <- setdiff(required, names(data))
  if (length(missing) > 0) {
    stop(filename, " is missing columns: ", paste(missing, collapse = ", "))
  }
  data
}

save_figure <- function(plot, filename, width, height) {
  ggsave(
    file.path(figure_dir, filename),
    plot = plot,
    width = width,
    height = height,
    units = "in",
    dpi = 300,
    bg = "white"
  )
}

frame_order <- c("Intensifying", "Informational", "Mitigating")
base_theme <- theme_minimal(base_size = 13) +
  theme(
    panel.grid.minor = element_blank(),
    plot.title = element_text(face = "bold"),
    legend.position = "top"
  )

distributions <- read_result(
  "frame_distributions.csv",
  c("modality", "label_en", "n", "percent")
)
if (nrow(distributions) != 6 || sum(distributions$n) != 898) {
  stop("Frame-distribution table does not represent two modalities across 449 videos")
}
distributions$label_en <- factor(distributions$label_en, levels = frame_order)
distributions$annotation <- sprintf("%d\n(%.1f%%)", distributions$n, 100 * distributions$percent)

figure1 <- ggplot(
  distributions,
  aes(x = label_en, y = percent, fill = modality)
) +
  geom_col(position = position_dodge(width = 0.74), width = 0.66) +
  geom_text(
    aes(label = annotation),
    position = position_dodge(width = 0.74),
    vjust = -0.2,
    lineheight = 0.9,
    size = 3.5
  ) +
  scale_fill_manual(values = c("Text" = "#BDBDBD", "Visual" = "#4D4D4D")) +
  scale_y_continuous(
    labels = function(x) sprintf("%d%%", round(100 * x)),
    limits = c(0, 0.68),
    expand = expansion(mult = c(0, 0.02))
  ) +
  labs(
    title = "Distribution of Textual and Visual Frames",
    x = NULL,
    y = "Share of videos",
    fill = NULL
  ) +
  base_theme
save_figure(figure1, "figure1_frame_distribution.png", 9, 5.6)

combinations <- read_result(
  "frame_combinations.csv",
  c(
    "visual_label_en", "text_label_en", "n", "row_percent",
    "standardized_residual"
  )
)
if (nrow(combinations) != 9 || sum(combinations$n) != 449) {
  stop("Frame-combination table does not represent the final 449-video sample")
}
combinations$visual_label_en <- factor(combinations$visual_label_en, levels = frame_order)
combinations$text_label_en <- factor(combinations$text_label_en, levels = frame_order)
combinations$annotation <- sprintf("n = %d\n%.1f%%", combinations$n, 100 * combinations$row_percent)

figure2 <- ggplot(
  combinations,
  aes(x = text_label_en, y = visual_label_en, fill = standardized_residual)
) +
  geom_tile(color = "white", linewidth = 1) +
  geom_text(aes(label = annotation), lineheight = 0.95, size = 3.7) +
  scale_fill_gradient2(
    low = "#D9D9D9",
    mid = "white",
    high = "#525252",
    midpoint = 0,
    name = "Standardized\nresidual"
  ) +
  labs(
    title = "Visual × Textual Frame Combinations",
    subtitle = "Cells show counts and row percentages",
    x = "Textual frame",
    y = "Visual frame"
  ) +
  base_theme +
  theme(panel.grid = element_blank())
save_figure(figure2, "figure2_frame_combinations.png", 8.5, 6.3)

anger <- read_result(
  "anger_by_frame_combination.csv",
  c("visual_label_en", "text_label_en", "n", "mean_anger_rate")
)
if (nrow(anger) != 9 || sum(anger$n) != 449) {
  stop("Anger-rate table does not represent the final 449-video sample")
}
anger$visual_label_en <- factor(anger$visual_label_en, levels = rev(frame_order))
anger$text_label_en <- factor(anger$text_label_en, levels = frame_order)
anger$annotation <- sprintf("%.3f\n(n = %d)", anger$mean_anger_rate, anger$n)

figure3 <- ggplot(
  anger,
  aes(x = text_label_en, y = visual_label_en, fill = mean_anger_rate)
) +
  geom_tile(color = "white", linewidth = 1) +
  geom_text(aes(label = annotation), lineheight = 0.95, size = 3.7) +
  scale_fill_gradient(
    low = "white",
    high = "#404040",
    limits = range(anger$mean_anger_rate),
    name = "Mean anger\nrate"
  ) +
  labs(
    title = "Mean Anger Rate by Visual–Textual Frame Combination",
    subtitle = "Cells show unweighted video-level means and sample sizes",
    x = "Textual frame",
    y = "Visual frame"
  ) +
  base_theme +
  theme(panel.grid = element_blank())
save_figure(figure3, "figure3_anger_rate.png", 8.5, 6.3)

cat("Figures generated from the final 449-video analysis:\n")
cat("- results/figures/reproduced/figure1_frame_distribution.png\n")
cat("- results/figures/reproduced/figure2_frame_combinations.png\n")
cat("- results/figures/reproduced/figure3_anger_rate.png\n")
