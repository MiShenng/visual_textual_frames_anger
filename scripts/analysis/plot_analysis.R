options(stringsAsFactors = FALSE)

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for plotting.")
}

library(ggplot2)

in_dir <- "analysis_tables"
out_dir <- "figures"
dir.create(out_dir, showWarnings = FALSE)

path2 <- file.path(in_dir, "table2_frame_distributions.csv")
path3 <- file.path(in_dir, "table3_visual_text_crosstab.csv")
path4 <- file.path(in_dir, "table4_anger_by_frame_combo.csv")
path_reg <- file.path(in_dir, "regression_nb_coefficients.csv")

for (p in c(path2, path3, path4, path_reg)) {
  if (!file.exists(p)) stop(sprintf("Missing input file: %s", p))
}

t2 <- read.csv(path2, fileEncoding = "UTF-8")
t3 <- read.csv(path3, fileEncoding = "UTF-8")
t4 <- read.csv(path4, fileEncoding = "UTF-8")
reg <- read.csv(path_reg, fileEncoding = "UTF-8")

frame_order <- c("缓释", "说明", "煽动")

# Figure 1: Frame distributions
t2$variable_cn <- ifelse(
  t2$variable == "text_arousal_label",
  "文本框架",
  ifelse(t2$variable == "visual_arousal_label", "视觉框架", t2$variable)
)
t2$level <- factor(t2$level, levels = frame_order)
t2$percent_label <- sprintf("%.1f%%", 100 * t2$percent)

p1 <- ggplot(t2, aes(x = level, y = percent, fill = variable_cn)) +
  geom_col(position = position_dodge(width = 0.75), width = 0.65) +
  geom_text(
    aes(label = percent_label),
    position = position_dodge(width = 0.75),
    vjust = -0.2,
    size = 3.8
  ) +
  scale_y_continuous(labels = function(x) sprintf("%d%%", round(x * 100)), limits = c(0, 0.7)) +
  scale_fill_manual(values = c("文本框架" = "#377eb8", "视觉框架" = "#e41a1c")) +
  labs(
    title = "图1  文本与视觉唤醒框架分布",
    x = "框架类别",
    y = "占比",
    fill = NULL
  ) +
  theme_minimal(base_size = 13) +
  theme(
    legend.position = "top",
    panel.grid.minor = element_blank(),
    plot.title = element_text(face = "bold")
  )

ggsave(
  filename = file.path(out_dir, "fig1_frame_distributions.png"),
  plot = p1,
  width = 9,
  height = 5.5,
  dpi = 300
)

# Figure 2: Visual x Text heatmap (row percent)
t3$visual_arousal_label <- factor(t3$visual_arousal_label, levels = frame_order)
t3$text_arousal_label <- factor(t3$text_arousal_label, levels = frame_order)
t3$label <- sprintf("n=%d\n%.1f%%", t3$n, 100 * t3$row_percent)

p2 <- ggplot(t3, aes(x = text_arousal_label, y = visual_arousal_label, fill = row_percent)) +
  geom_tile(color = "white", linewidth = 0.8) +
  geom_text(aes(label = label), size = 3.6) +
  scale_fill_gradient(low = "#deebf7", high = "#08519c", labels = function(x) sprintf("%d%%", round(x * 100))) +
  labs(
    title = "图2  视觉框架 × 文本框架（行百分比）",
    x = "文本框架",
    y = "视觉框架",
    fill = "行占比"
  ) +
  theme_minimal(base_size = 13) +
  theme(
    panel.grid = element_blank(),
    plot.title = element_text(face = "bold")
  )

ggsave(
  filename = file.path(out_dir, "fig2_visual_text_heatmap.png"),
  plot = p2,
  width = 8.5,
  height = 6.5,
  dpi = 300
)

# Figure 3: Anger rate by frame combination
t4$frame_combo <- factor(t4$frame_combo, levels = t4$frame_combo[order(t4$anger_rate_mean)])
t4$n_label <- sprintf("n=%d", t4$n_videos)

p3 <- ggplot(t4, aes(x = frame_combo, y = anger_rate_mean)) +
  geom_linerange(aes(ymin = anger_rate_p25, ymax = anger_rate_p75), color = "#969696", linewidth = 1.2) +
  geom_point(color = "#d95f02", size = 3.2) +
  geom_text(aes(label = n_label), hjust = -0.2, size = 3.4) +
  coord_flip() +
  scale_y_continuous(limits = c(0, max(t4$anger_rate_p75, na.rm = TRUE) * 1.15)) +
  labs(
    title = "图3  不同框架组合下的愤怒率（点=均值，线=IQR）",
    x = "视觉 × 文本组合",
    y = "anger_rate"
  ) +
  theme_minimal(base_size = 13) +
  theme(
    panel.grid.minor = element_blank(),
    plot.title = element_text(face = "bold")
  )

ggsave(
  filename = file.path(out_dir, "fig3_anger_rate_by_combo.png"),
  plot = p3,
  width = 10,
  height = 6.2,
  dpi = 300
)

# Figure 4: Regression IRR forest
reg <- reg[reg$term != "(Intercept)", ]

clean_term <- function(x) {
  x <- gsub("text_arousal_label", "文本=", x, fixed = TRUE)
  x <- gsub("visual_arousal_label", "视觉=", x, fixed = TRUE)
  x <- gsub(":", " × ", x, fixed = TRUE)
  x <- gsub("publish_day_index", "发布时间(日序)", x, fixed = TRUE)
  x <- gsub("visual_segment_count", "视觉片段数", x, fixed = TRUE)
  x <- gsub("visual_total_duration", "视觉总时长", x, fixed = TRUE)
  x <- gsub("image_text_count", "画面嵌字数", x, fixed = TRUE)
  x
}

reg$term_cn <- clean_term(reg$term)
reg$sig <- ifelse(reg$p_value < 0.05, "p < 0.05", "n.s.")
reg$term_cn <- factor(reg$term_cn, levels = rev(reg$term_cn))

p4 <- ggplot(reg, aes(x = irr, y = term_cn, color = sig)) +
  geom_vline(xintercept = 1, linetype = "dashed", color = "#636363") +
  geom_errorbarh(aes(xmin = irr_ci_low, xmax = irr_ci_high), height = 0.2, linewidth = 0.9) +
  geom_point(size = 2.8) +
  scale_x_log10() +
  scale_color_manual(values = c("p < 0.05" = "#e41a1c", "n.s." = "#377eb8")) +
  labs(
    title = "图4  负二项回归 IRR（95%CI）",
    x = "IRR（对数坐标）",
    y = NULL,
    color = NULL
  ) +
  theme_minimal(base_size = 13) +
  theme(
    legend.position = "top",
    panel.grid.minor = element_blank(),
    plot.title = element_text(face = "bold")
  )

ggsave(
  filename = file.path(out_dir, "fig4_regression_irr_forest.png"),
  plot = p4,
  width = 11,
  height = 7.2,
  dpi = 300
)

cat("Plots generated in figures/:\n")
cat("- fig1_frame_distributions.png\n")
cat("- fig2_visual_text_heatmap.png\n")
cat("- fig3_anger_rate_by_combo.png\n")
cat("- fig4_regression_irr_forest.png\n")
