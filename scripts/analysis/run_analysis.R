options(stringsAsFactors = FALSE)

safe_quantile <- function(x, p) {
  x <- x[!is.na(x)]
  if (length(x) == 0) return(NA_real_)
  as.numeric(stats::quantile(x, probs = p, names = FALSE, type = 7))
}

parse_datetime <- function(x) {
  fmts <- c(
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d"
  )
  out <- rep(as.POSIXct(NA), length(x))
  for (f in fmts) {
    idx <- is.na(out)
    if (!any(idx)) break
    parsed <- as.POSIXct(x[idx], format = f, tz = "Asia/Shanghai")
    out[idx] <- parsed
  }
  out
}

freq_table <- function(vec, varname) {
  vec <- ifelse(is.na(vec) | trimws(vec) == "", "<NA>", trimws(as.character(vec)))
  tab <- as.data.frame(table(vec), stringsAsFactors = FALSE)
  names(tab) <- c("level", "n")
  tab$variable <- varname
  tab$percent <- tab$n / sum(tab$n)
  tab <- tab[order(-tab$n, tab$level), c("variable", "level", "n", "percent")]
  rownames(tab) <- NULL
  tab
}

if (!file.exists("reference2.csv")) {
  stop("reference2.csv not found in current directory")
}

df <- read.csv("reference2.csv", stringsAsFactors = FALSE)
dir.create("analysis_tables", showWarnings = FALSE)

for (col in c("text_arousal_label", "visual_arousal_label", "text_arousal_confidence")) {
  if (col %in% names(df)) df[[col]] <- trimws(as.character(df[[col]]))
}

if ("publish_time" %in% names(df)) {
  df$publish_datetime <- parse_datetime(df$publish_time)
  df$publish_date <- as.Date(df$publish_datetime)
}

if ("text_arousal_confidence" %in% names(df)) {
  df$text_arousal_confidence_num <- suppressWarnings(as.numeric(df$text_arousal_confidence))
}

num_candidates <- c(
  "comment_count", "visual_segment_count", "visual_total_duration", "image_text_count",
  "comment_count_effective", "anger_count", "anger_rate", "anger_mean_score",
  "visual_arousal_share", "text_arousal_confidence_num"
)
num_cols <- num_candidates[num_candidates %in% names(df)]

num_desc <- do.call(rbind, lapply(num_cols, function(col) {
  x <- suppressWarnings(as.numeric(df[[col]]))
  data.frame(
    variable = col,
    n = sum(!is.na(x)),
    missing = sum(is.na(x)),
    mean = mean(x, na.rm = TRUE),
    sd = stats::sd(x, na.rm = TRUE),
    median = stats::median(x, na.rm = TRUE),
    p25 = safe_quantile(x, 0.25),
    p75 = safe_quantile(x, 0.75),
    min = ifelse(all(is.na(x)), NA_real_, min(x, na.rm = TRUE)),
    max = ifelse(all(is.na(x)), NA_real_, max(x, na.rm = TRUE))
  )
}))

cat_desc_list <- list()
for (col in c("text_arousal_label", "visual_arousal_label", "image_text_has_content")) {
  if (col %in% names(df)) cat_desc_list[[length(cat_desc_list) + 1]] <- freq_table(df[[col]], col)
}
if ("publish_date" %in% names(df)) {
  ym <- ifelse(is.na(df$publish_date), NA, format(df$publish_date, "%Y-%m"))
  cat_desc_list[[length(cat_desc_list) + 1]] <- freq_table(ym, "publish_year_month")
}
cat_desc <- do.call(rbind, cat_desc_list)

write.csv(num_desc, "analysis_tables/table1_numeric_descriptive.csv", row.names = FALSE, fileEncoding = "UTF-8")
write.csv(cat_desc, "analysis_tables/table1_categorical_descriptive.csv", row.names = FALSE, fileEncoding = "UTF-8")

text_dist <- freq_table(df$text_arousal_label, "text_arousal_label")
visual_dist <- freq_table(df$visual_arousal_label, "visual_arousal_label")
table2 <- rbind(text_dist, visual_dist)
write.csv(table2, "analysis_tables/table2_frame_distributions.csv", row.names = FALSE, fileEncoding = "UTF-8")

ct <- table(df$visual_arousal_label, df$text_arousal_label)
chi <- suppressWarnings(chisq.test(ct, correct = FALSE))
n_total <- sum(ct)
cramers_v <- sqrt(as.numeric(chi$statistic) / (n_total * (min(dim(ct)) - 1)))

ct_long <- as.data.frame(ct, stringsAsFactors = FALSE)
names(ct_long) <- c("visual_arousal_label", "text_arousal_label", "n")
ct_row_pct <- as.data.frame(as.table(prop.table(ct, margin = 1)), stringsAsFactors = FALSE)
ct_col_pct <- as.data.frame(as.table(prop.table(ct, margin = 2)), stringsAsFactors = FALSE)
ct_exp <- as.data.frame(as.table(chi$expected), stringsAsFactors = FALSE)
names(ct_row_pct)[1:2] <- c("visual_arousal_label", "text_arousal_label")
names(ct_col_pct)[1:2] <- c("visual_arousal_label", "text_arousal_label")
names(ct_exp)[1:2] <- c("visual_arousal_label", "text_arousal_label")
names(ct_row_pct)[3] <- "row_percent"
names(ct_col_pct)[3] <- "col_percent"
names(ct_exp)[3] <- "expected_n"

ct_out <- merge(ct_long, ct_row_pct, by = c("visual_arousal_label", "text_arousal_label"))
ct_out <- merge(ct_out, ct_col_pct, by = c("visual_arousal_label", "text_arousal_label"))
ct_out <- merge(ct_out, ct_exp, by = c("visual_arousal_label", "text_arousal_label"))
ct_out <- ct_out[order(ct_out$visual_arousal_label, ct_out$text_arousal_label), ]

chi_meta <- data.frame(
  statistic = as.numeric(chi$statistic),
  df = as.numeric(chi$parameter),
  p_value = as.numeric(chi$p.value),
  cramers_v = as.numeric(cramers_v),
  n_total = n_total
)

write.csv(ct_out, "analysis_tables/table3_visual_text_crosstab.csv", row.names = FALSE, fileEncoding = "UTF-8")
write.csv(chi_meta, "analysis_tables/table3_chi_square_meta.csv", row.names = FALSE, fileEncoding = "UTF-8")

df$frame_combo <- paste(df$visual_arousal_label, "×", df$text_arousal_label)
combo_levels <- sort(unique(df$frame_combo))

combo_stats <- do.call(rbind, lapply(combo_levels, function(cb) {
  d <- df[df$frame_combo == cb, ]
  ar <- suppressWarnings(as.numeric(d$anger_rate))
  am <- suppressWarnings(as.numeric(d$anger_mean_score))
  data.frame(
    frame_combo = cb,
    n_videos = nrow(d),
    anger_rate_mean = mean(ar, na.rm = TRUE),
    anger_rate_median = stats::median(ar, na.rm = TRUE),
    anger_rate_p25 = safe_quantile(ar, 0.25),
    anger_rate_p75 = safe_quantile(ar, 0.75),
    anger_mean_score_mean = mean(am, na.rm = TRUE),
    anger_mean_score_median = stats::median(am, na.rm = TRUE),
    anger_mean_score_p25 = safe_quantile(am, 0.25),
    anger_mean_score_p75 = safe_quantile(am, 0.75)
  )
}))

combo_stats <- combo_stats[order(-combo_stats$anger_rate_mean), ]
write.csv(combo_stats, "analysis_tables/table4_anger_by_frame_combo.csv", row.names = FALSE, fileEncoding = "UTF-8")

if (!requireNamespace("MASS", quietly = TRUE)) {
  stop("R package MASS is required but not available")
}

model_df <- df
num_need <- c("anger_count", "comment_count_effective", "visual_segment_count", "visual_total_duration", "image_text_count")
for (col in num_need) {
  model_df[[col]] <- suppressWarnings(as.numeric(model_df[[col]]))
}

if ("publish_date" %in% names(model_df)) {
  min_date <- min(model_df$publish_date, na.rm = TRUE)
  if (is.finite(min_date)) {
    model_df$publish_day_index <- as.numeric(model_df$publish_date - min_date)
  } else {
    model_df$publish_day_index <- NA_real_
  }
} else {
  model_df$publish_day_index <- NA_real_
}

model_df <- model_df[
  !is.na(model_df$anger_count) &
    !is.na(model_df$comment_count_effective) &
    model_df$comment_count_effective > 0 &
    !is.na(model_df$text_arousal_label) & trimws(model_df$text_arousal_label) != "" &
    !is.na(model_df$visual_arousal_label) & trimws(model_df$visual_arousal_label) != "",
]

for (col in c("visual_segment_count", "visual_total_duration", "image_text_count", "publish_day_index")) {
  med <- stats::median(model_df[[col]], na.rm = TRUE)
  if (!is.finite(med)) med <- 0
  model_df[[col]][is.na(model_df[[col]])] <- med
}

model_df$text_arousal_label <- factor(model_df$text_arousal_label)
model_df$visual_arousal_label <- factor(model_df$visual_arousal_label)

if ("缓释" %in% levels(model_df$text_arousal_label)) {
  model_df$text_arousal_label <- stats::relevel(model_df$text_arousal_label, ref = "缓释")
}
if ("缓释" %in% levels(model_df$visual_arousal_label)) {
  model_df$visual_arousal_label <- stats::relevel(model_df$visual_arousal_label, ref = "缓释")
}

nb_fit <- MASS::glm.nb(
  anger_count ~ text_arousal_label * visual_arousal_label +
    visual_segment_count + visual_total_duration + image_text_count + publish_day_index +
    offset(log(comment_count_effective)),
  data = model_df
)

sm <- summary(nb_fit)
coef_mat <- sm$coefficients
coef_df <- data.frame(
  term = rownames(coef_mat),
  estimate = coef_mat[, "Estimate"],
  std_error = coef_mat[, "Std. Error"],
  z_value = coef_mat[, "z value"],
  p_value = coef_mat[, "Pr(>|z|)"],
  irr = exp(coef_mat[, "Estimate"]),
  irr_ci_low = exp(coef_mat[, "Estimate"] - 1.96 * coef_mat[, "Std. Error"]),
  irr_ci_high = exp(coef_mat[, "Estimate"] + 1.96 * coef_mat[, "Std. Error"]),
  row.names = NULL
)

fit_df <- data.frame(
  model = "Negative Binomial (anger_count with log(comment_count_effective) offset)",
  n = nrow(model_df),
  aic = AIC(nb_fit),
  theta = nb_fit$theta,
  logLik = as.numeric(logLik(nb_fit))
)

write.csv(coef_df, "analysis_tables/regression_nb_coefficients.csv", row.names = FALSE, fileEncoding = "UTF-8")
write.csv(fit_df, "analysis_tables/regression_nb_fit.csv", row.names = FALSE, fileEncoding = "UTF-8")

text_top <- text_dist[order(-text_dist$n), c("level", "n", "percent")]
visual_top <- visual_dist[order(-visual_dist$n), c("level", "n", "percent")]

report_lines <- c(
  "# 分析结果汇总",
  "",
  sprintf("- 样本量: %d 条视频", nrow(df)),
  sprintf("- 字段数: %d 列", ncol(df)),
  "",
  "## 表1 样本描述统计",
  "- 文件: analysis_tables/table1_numeric_descriptive.csv",
  "- 文件: analysis_tables/table1_categorical_descriptive.csv",
  "",
  "## 表2 文本与视觉框架分布",
  sprintf("- 文本框架主导: %s (%d, %.2f%%)", text_top$level[1], text_top$n[1], 100 * text_top$percent[1]),
  sprintf("- 视觉框架主导: %s (%d, %.2f%%)", visual_top$level[1], visual_top$n[1], 100 * visual_top$percent[1]),
  "- 文件: analysis_tables/table2_frame_distributions.csv",
  "",
  "## 表3 列联与独立性检验",
  sprintf("- 卡方统计量: %.4f", chi_meta$statistic),
  sprintf("- 自由度: %d", as.integer(chi_meta$df)),
  sprintf("- p值: %.6g", chi_meta$p_value),
  sprintf("- Cramer's V: %.4f", chi_meta$cramers_v),
  "- 文件: analysis_tables/table3_visual_text_crosstab.csv",
  "- 文件: analysis_tables/table3_chi_square_meta.csv",
  "",
  "## 表4 组合与愤怒表达",
  "- 文件: analysis_tables/table4_anger_by_frame_combo.csv",
  "",
  "## 回归表",
  "- 模型: 负二项回归 (anger_count, offset=log(comment_count_effective))",
  "- 文件: analysis_tables/regression_nb_coefficients.csv",
  "- 文件: analysis_tables/regression_nb_fit.csv"
)

writeLines(report_lines, con = "analysis_report.md", useBytes = TRUE)
cat("Analysis completed. Outputs written to analysis_tables/ and analysis_report.md\n")
