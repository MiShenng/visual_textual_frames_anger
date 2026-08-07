options(stringsAsFactors = FALSE)

input_path <- "data/processed/video_level_master_449.csv"
table_dir <- "results/tables"
dir.create(table_dir, recursive = TRUE, showWarnings = FALSE)

write_utf8_csv <- function(x, filename) {
  write.csv(
    x,
    file.path(table_dir, filename),
    row.names = FALSE,
    fileEncoding = "UTF-8"
  )
}

require_columns <- function(data, columns) {
  missing <- setdiff(columns, names(data))
  if (length(missing) > 0) {
    stop("Missing required columns: ", paste(missing, collapse = ", "))
  }
}

model_comparison_row <- function(reduced, full, effect) {
  comparison <- anova(reduced, full)
  data.frame(
    effect = effect,
    df = comparison$Df[2],
    residual_df = comparison$Res.Df[2],
    sum_sq = comparison$`Sum of Sq`[2],
    f_value = comparison$F[2],
    p_value = comparison$`Pr(>F)`[2]
  )
}

paper_order <- c("Intensifying", "Informational", "Mitigating")
model_order <- rev(paper_order)
label_map <- setNames(paper_order, paper_order)

if (!file.exists(input_path)) {
  stop("Missing analytic data: ", input_path)
}

df <- read.csv(input_path, fileEncoding = "UTF-8", check.names = FALSE)
required <- c(
  "case_id", "platform_video_id", "video_url", "like_count", "follower_count",
  "published_at", "comment_count",
  "visual_main_arousal_label", "visual_main_arousal_share",
  "text_arousal_label", "text_arousal_confidence",
  "comment_count_effective", "anger_count", "anger_rate"
)
require_columns(df, required)

numeric_columns <- c(
  "like_count", "follower_count", "comment_count", "visual_main_arousal_share",
  "comment_count_effective", "anger_count", "anger_rate"
)
for (column in numeric_columns) {
  df[[column]] <- suppressWarnings(as.numeric(df[[column]]))
}

if (nrow(df) != 449) stop("Expected 449 videos; found ", nrow(df))
if (anyDuplicated(df$case_id)) stop("case_id must be unique")
if (anyDuplicated(df$platform_video_id)) stop("platform_video_id must be unique")
if (any(!nzchar(trimws(df$platform_video_id)))) stop("platform_video_id must not be blank")
if (any(!nzchar(trimws(df$video_url)))) stop("video_url must not be blank")
if (anyNA(df[required])) stop("Required analytic fields contain missing values")
if (any(!is.finite(as.matrix(df[numeric_columns])))) stop("Numeric analytic fields must be finite")
if (any(df[c("like_count", "follower_count", "comment_count", "comment_count_effective", "anger_count")] < 0)) {
  stop("Counts must be non-negative")
}
if (any(df$comment_count_effective <= 0)) stop("comment_count_effective must be positive")
if (any(df$anger_count > df$comment_count_effective)) stop("anger_count exceeds effective comments")
if (any(df$anger_rate < 0 | df$anger_rate > 1)) stop("anger_rate must be within [0, 1]")

rate_error <- abs(df$anger_rate - df$anger_count / df$comment_count_effective)
if (max(rate_error) > 1e-9) stop("anger_rate arithmetic check failed")

visual_counts <- table(factor(df$visual_main_arousal_label, levels = paper_order))
text_counts <- table(factor(df$text_arousal_label, levels = paper_order))
if (!identical(as.integer(visual_counts), c(68L, 189L, 192L))) {
  stop("Visual-frame distribution does not match the final 449-video manuscript sample")
}
if (!identical(as.integer(text_counts), c(78L, 111L, 260L))) {
  stop("Text-frame distribution does not match the final 449-video manuscript sample")
}
if (sum(df$comment_count_effective) != 419126) stop("Expected 419,126 effective comments")
if (sum(df$anger_count) != 48973) stop("Expected 48,973 anger-classified comments")

df$published_date <- as.Date(df$published_at)
if (anyNA(df$published_date)) stop("published_at contains unparseable dates")
df$publish_day <- as.numeric(df$published_date - min(df$published_date))
df$visual_main_arousal_label <- factor(df$visual_main_arousal_label, levels = model_order)
df$text_arousal_label <- factor(df$text_arousal_label, levels = model_order)

sample_summary <- data.frame(
  metric = c(
    "n_videos", "effective_comments", "mean_comments_per_video", "anger_comments",
    "weighted_anger_share", "video_anger_rate_mean", "video_anger_rate_median",
    "published_date_min", "published_date_max", "videos_after_2026_02_20"
  ),
  value = c(
    nrow(df),
    sum(df$comment_count_effective),
    mean(df$comment_count_effective),
    sum(df$anger_count),
    sum(df$anger_count) / sum(df$comment_count_effective),
    mean(df$anger_rate),
    median(df$anger_rate),
    as.character(min(df$published_date)),
    as.character(max(df$published_date)),
    sum(df$published_date > as.Date("2026-02-20"))
  )
)
write_utf8_csv(sample_summary, "sample_summary.csv")

distribution_for <- function(values, modality) {
  counts <- table(factor(values, levels = paper_order))
  data.frame(
    modality = modality,
    label = names(counts),
    label_en = unname(label_map[names(counts)]),
    n = as.integer(counts),
    percent = as.integer(counts) / sum(counts)
  )
}

frame_distributions <- rbind(
  distribution_for(as.character(df$text_arousal_label), "Text"),
  distribution_for(as.character(df$visual_main_arousal_label), "Visual")
)
write_utf8_csv(frame_distributions, "frame_distributions.csv")

cross_tab <- table(
  factor(df$visual_main_arousal_label, levels = paper_order),
  factor(df$text_arousal_label, levels = paper_order)
)
chi <- chisq.test(cross_tab, correct = FALSE)
cross_long <- as.data.frame(cross_tab, stringsAsFactors = FALSE)
names(cross_long) <- c("visual_label", "text_label", "n")
cross_long$visual_label_en <- unname(label_map[cross_long$visual_label])
cross_long$text_label_en <- unname(label_map[cross_long$text_label])
cross_long$row_percent <- as.vector(prop.table(cross_tab, margin = 1))
cross_long$expected_n <- as.vector(chi$expected)
cross_long$standardized_residual <- as.vector(chi$stdres)
cross_long <- cross_long[, c(
  "visual_label", "visual_label_en", "text_label", "text_label_en", "n",
  "row_percent", "expected_n", "standardized_residual"
)]
row_percent_sums <- aggregate(row_percent ~ visual_label, cross_long, sum)
if (any(abs(row_percent_sums$row_percent - 1) > 1e-12)) {
  stop("Frame-combination row percentages do not sum to one")
}
write_utf8_csv(cross_long, "frame_combinations.csv")

cramers_v <- sqrt(as.numeric(chi$statistic) / (sum(cross_tab) * (min(dim(cross_tab)) - 1)))
chi_summary <- data.frame(
  statistic = as.numeric(chi$statistic),
  df = as.integer(chi$parameter),
  p_value = chi$p.value,
  cramers_v = cramers_v,
  n = sum(cross_tab)
)
write_utf8_csv(chi_summary, "chi_square_summary.csv")

df$frame_combination <- interaction(
  factor(df$visual_main_arousal_label, levels = paper_order),
  factor(df$text_arousal_label, levels = paper_order),
  sep = " × ",
  drop = TRUE
)

combination_rows <- lapply(levels(df$frame_combination), function(combination) {
  values <- df$anger_rate[df$frame_combination == combination]
  parts <- strsplit(combination, " × ", fixed = TRUE)[[1]]
  data.frame(
    visual_label = parts[1],
    visual_label_en = unname(label_map[parts[1]]),
    text_label = parts[2],
    text_label_en = unname(label_map[parts[2]]),
    n = length(values),
    mean_anger_rate = mean(values),
    median_anger_rate = median(values),
    sd_anger_rate = sd(values)
  )
})
anger_by_combination <- do.call(rbind, combination_rows)
write_utf8_csv(anger_by_combination, "anger_by_frame_combination.csv")

kw <- kruskal.test(anger_rate ~ frame_combination, data = df)
kw_summary <- data.frame(
  statistic = as.numeric(kw$statistic),
  df = as.integer(kw$parameter),
  p_value = kw$p.value,
  n = nrow(df)
)
write_utf8_csv(kw_summary, "kruskal_wallis_summary.csv")

full_anova <- aov(
  anger_rate ~ visual_main_arousal_label * text_arousal_label,
  data = df
)
anova_table <- summary(full_anova)[[1]]
residual_ss <- anova_table["Residuals", "Sum Sq"]
effect_names <- c("Visual Frame", "Text Frame", "Visual × Text", "Residual")
anova_output <- data.frame(
  effect = effect_names,
  sum_sq = anova_table[, "Sum Sq"],
  df = anova_table[, "Df"],
  mean_sq = anova_table[, "Mean Sq"],
  f_value = anova_table[, "F value"],
  p_value = anova_table[, "Pr(>F)"],
  partial_eta_sq = c(
    anova_table[1, "Sum Sq"] / (anova_table[1, "Sum Sq"] + residual_ss),
    anova_table[2, "Sum Sq"] / (anova_table[2, "Sum Sq"] + residual_ss),
    anova_table[3, "Sum Sq"] / (anova_table[3, "Sum Sq"] + residual_ss),
    NA_real_
  )
)
anova_output <- rbind(
  anova_output,
  data.frame(
    effect = "Total",
    sum_sq = sum((df$anger_rate - mean(df$anger_rate))^2),
    df = nrow(df) - 1,
    mean_sq = NA_real_,
    f_value = NA_real_,
    p_value = NA_real_,
    partial_eta_sq = NA_real_
  )
)
write_utf8_csv(anova_output, "table3_two_way_anova.csv")

main_effects_model <- lm(
  anger_rate ~ visual_main_arousal_label + text_arousal_label,
  data = df
)
main_effects_type2 <- rbind(
  model_comparison_row(
    lm(anger_rate ~ text_arousal_label, data = df),
    main_effects_model,
    "Visual Frame"
  ),
  model_comparison_row(
    lm(anger_rate ~ visual_main_arousal_label, data = df),
    main_effects_model,
    "Text Frame"
  )
)
write_utf8_csv(main_effects_type2, "main_effects_type2_tests.csv")

fractional_model <- glm(
  anger_rate ~ visual_main_arousal_label * text_arousal_label,
  data = df,
  family = quasibinomial(link = "logit")
)
prediction_grid <- expand.grid(
  visual_main_arousal_label = factor(paper_order, levels = model_order),
  text_arousal_label = factor(paper_order, levels = model_order)
)
fractional_prediction <- predict(
  fractional_model,
  newdata = prediction_grid,
  type = "link",
  se.fit = TRUE
)
inverse_logit <- function(x) stats::plogis(x)
prediction_grid$visual_label_en <- unname(label_map[as.character(prediction_grid$visual_main_arousal_label)])
prediction_grid$text_label_en <- unname(label_map[as.character(prediction_grid$text_arousal_label)])
prediction_grid$predicted_anger_rate <- inverse_logit(fractional_prediction$fit)
prediction_grid$ci_low <- inverse_logit(fractional_prediction$fit - 1.96 * fractional_prediction$se.fit)
prediction_grid$ci_high <- inverse_logit(fractional_prediction$fit + 1.96 * fractional_prediction$se.fit)
write_utf8_csv(prediction_grid, "fractional_logit_predictions.csv")

controlled_model <- lm(
  anger_rate ~ visual_main_arousal_label + text_arousal_label +
    log1p(like_count) + log1p(follower_count) + publish_day,
  data = df
)
if (nobs(controlled_model) != nrow(df)) stop("Controlled OLS did not use all 449 videos")
controlled_coefficients <- as.data.frame(coef(summary(controlled_model)))
controlled_coefficients$term <- rownames(controlled_coefficients)
rownames(controlled_coefficients) <- NULL
names(controlled_coefficients)[1:4] <- c("estimate", "std_error", "t_value", "p_value")
controlled_coefficients <- controlled_coefficients[, c("term", "estimate", "std_error", "t_value", "p_value")]
write_utf8_csv(controlled_coefficients, "controlled_ols_coefficients.csv")

control_terms <- c("log1p(like_count)", "log1p(follower_count)", "publish_day")
controlled_tests <- rbind(
  model_comparison_row(
    lm(
      reformulate(c("text_arousal_label", control_terms), response = "anger_rate"),
      data = df
    ),
    controlled_model,
    "Visual Frame"
  ),
  model_comparison_row(
    lm(
      reformulate(c("visual_main_arousal_label", control_terms), response = "anger_rate"),
      data = df
    ),
    controlled_model,
    "Text Frame"
  )
)

controlled_interaction_model <- lm(
  anger_rate ~ visual_main_arousal_label * text_arousal_label +
    log1p(like_count) + log1p(follower_count) + publish_day,
  data = df
)
controlled_tests <- rbind(
  controlled_tests,
  model_comparison_row(controlled_model, controlled_interaction_model, "Visual × Text")
)
write_utf8_csv(controlled_tests, "controlled_ols_tests.csv")

if (abs(chi_summary$statistic - 50.171303128166) > 1e-8) stop("Chi-square validation failed")
if (abs(kw_summary$statistic - 50.983870603976) > 1e-8) stop("Kruskal-Wallis validation failed")
if (abs(anova_output$f_value[1] - 17.7363) > 1e-3) stop("Visual ANOVA validation failed")
if (abs(anova_output$f_value[2] - 5.5088) > 1e-3) stop("Text ANOVA validation failed")
if (abs(anova_output$f_value[3] - 0.2771) > 1e-3) stop("Interaction ANOVA validation failed")
if (abs(main_effects_type2$f_value[1] - 13.89) > 0.01) stop("Type-II visual test validation failed")

cat("Analysis complete: final 449-video manuscript sample validated.\n")
cat("Tables written to", table_dir, "\n")
