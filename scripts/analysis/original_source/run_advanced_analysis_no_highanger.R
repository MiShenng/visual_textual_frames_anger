options(stringsAsFactors = FALSE)

input_path <- "/Volumes/黎鑿/4.1 AEJMC/final.csv"
out_dir <- "/Volumes/黎鑿/4.1 AEJMC/analysis_advanced_no_highanger"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

write_csv <- function(df, path) {
  write.csv(df, path, row.names = FALSE, fileEncoding = "UTF-8")
}

read_final <- function(path) {
  # Try UTF-8-BOM first, fallback to UTF-8.
  x <- tryCatch(
    read.csv(path, fileEncoding = "UTF-8-BOM", check.names = FALSE),
    error = function(e) read.csv(path, fileEncoding = "UTF-8", check.names = FALSE)
  )
  x
}

to_num <- function(x) suppressWarnings(as.numeric(x))

hc3_lm <- function(formula, data) {
  fit <- lm(formula, data = data)
  X <- model.matrix(fit)
  e <- residuals(fit)
  h <- lm.influence(fit, do.coef = FALSE)$hat

  # HC3 covariance
  k <- ncol(X)
  meat <- matrix(0, nrow = k, ncol = k)
  for (i in seq_len(nrow(X))) {
    xi <- matrix(X[i, ], ncol = 1)
    denom <- (1 - h[i])
    if (is.na(denom) || abs(denom) < 1e-12) next
    s2 <- (e[i] / denom)^2
    meat <- meat + s2 * (xi %*% t(xi))
  }

  XtX <- t(X) %*% X
  XtX_inv <- solve(XtX)
  vcov_hc3 <- XtX_inv %*% meat %*% XtX_inv

  beta <- coef(fit)
  se <- sqrt(diag(vcov_hc3))
  df_res <- nrow(X) - ncol(X)
  t_val <- beta / se
  p_val <- 2 * pt(abs(t_val), df = df_res, lower.tail = FALSE)
  crit <- qt(0.975, df = df_res)

  tbl <- data.frame(
    term = names(beta),
    estimate = as.numeric(beta),
    se_hc3 = as.numeric(se),
    t_value = as.numeric(t_val),
    p_value = as.numeric(p_val),
    ci_low = as.numeric(beta - crit * se),
    ci_high = as.numeric(beta + crit * se),
    stringsAsFactors = FALSE
  )

  list(
    fit = fit,
    table = tbl,
    n = nrow(X),
    r2 = summary(fit)$r.squared,
    adj_r2 = summary(fit)$adj.r.squared
  )
}

safe_pairwise_wilcox <- function(y, g) {
  out <- pairwise.wilcox.test(y, g, p.adjust.method = "holm", exact = FALSE)
  pmat <- as.data.frame(as.table(out$p.value), stringsAsFactors = FALSE)
  names(pmat) <- c("group_1", "group_2", "p_value_holm")
  pmat <- pmat[!is.na(pmat$p_value_holm), ]
  pmat
}

winsorize <- function(x, p = c(0.01, 0.99)) {
  q <- quantile(x, probs = p, na.rm = TRUE, names = FALSE)
  pmin(pmax(x, q[1]), q[2])
}

# -------------------- Load and prepare --------------------
df <- read_final(input_path)

num_cols <- c("comment_count", "comment_count_effective", "anger_count", "anger_mean_score", "anger_rate", "visual_main_arousal_share")
for (cname in num_cols) {
  if (cname %in% names(df)) df[[cname]] <- to_num(df[[cname]])
}

# Drop rows with missing core fields (should be none in current table)
df <- df[!is.na(df$anger_rate) & !is.na(df$comment_count_effective), ]

# Build controls and factors
df$log_comment_count <- log1p(df$comment_count_effective)
df$visual_main_arousal_label <- factor(df$visual_main_arousal_label, levels = c("说明", "缓释", "煽动"))
df$text_arousal_label <- factor(df$text_arousal_label, levels = c("说明", "缓释", "煽动"))
# Keep confidence as factor; if level absent, R handles it.
df$text_arousal_confidence <- factor(df$text_arousal_confidence)

# -------------------- Significance tests --------------------
kw_visual <- kruskal.test(anger_rate ~ visual_main_arousal_label, data = df)
kw_text <- kruskal.test(anger_rate ~ text_arousal_label, data = df)

anova_visual <- summary(aov(anger_rate ~ visual_main_arousal_label, data = df))[[1]]
anova_text <- summary(aov(anger_rate ~ text_arousal_label, data = df))[[1]]

pair_visual <- safe_pairwise_wilcox(df$anger_rate, df$visual_main_arousal_label)
pair_visual$dimension <- "visual_main_arousal_label"
pair_text <- safe_pairwise_wilcox(df$anger_rate, df$text_arousal_label)
pair_text$dimension <- "text_arousal_label"

xt <- table(df$visual_main_arousal_label, df$text_arousal_label)
chi_vt <- chisq.test(xt)

cor_spearman <- suppressWarnings(cor.test(df$comment_count_effective, df$anger_rate, method = "spearman", exact = FALSE))

sig_overview <- data.frame(
  test = c(
    "Kruskal-Wallis: anger_rate ~ visual_main_arousal_label",
    "Kruskal-Wallis: anger_rate ~ text_arousal_label",
    "ANOVA: anger_rate ~ visual_main_arousal_label",
    "ANOVA: anger_rate ~ text_arousal_label",
    "Chi-square: visual_main_arousal_label x text_arousal_label",
    "Spearman: comment_count_effective vs anger_rate"
  ),
  statistic = c(
    as.numeric(kw_visual$statistic),
    as.numeric(kw_text$statistic),
    as.numeric(anova_visual[1, "F value"]),
    as.numeric(anova_text[1, "F value"]),
    as.numeric(chi_vt$statistic),
    as.numeric(cor_spearman$statistic)
  ),
  df = c(
    as.numeric(kw_visual$parameter),
    as.numeric(kw_text$parameter),
    as.numeric(anova_visual[1, "Df"]),
    as.numeric(anova_text[1, "Df"]),
    as.numeric(chi_vt$parameter),
    NA
  ),
  p_value = c(
    kw_visual$p.value,
    kw_text$p.value,
    as.numeric(anova_visual[1, "Pr(>F)"]),
    as.numeric(anova_text[1, "Pr(>F)"]),
    chi_vt$p.value,
    cor_spearman$p.value
  ),
  stringsAsFactors = FALSE
)

write_csv(sig_overview, file.path(out_dir, "significance_overview.csv"))
write_csv(rbind(pair_visual, pair_text), file.path(out_dir, "pairwise_wilcoxon_holm.csv"))

# -------------------- Regressions (no high_anger_flag) --------------------
form_base <- anger_rate ~ visual_main_arousal_label + text_arousal_label + log_comment_count
form_ext <- anger_rate ~ visual_main_arousal_label + text_arousal_label + log_comment_count + visual_main_arousal_share + text_arousal_confidence

m_base <- hc3_lm(form_base, df)
m_ext <- hc3_lm(form_ext, df)

reg_main <- rbind(
  transform(m_base$table, model = "M1_base"),
  transform(m_ext$table, model = "M2_extended")
)
reg_main <- reg_main[, c("model", "term", "estimate", "se_hc3", "t_value", "p_value", "ci_low", "ci_high")]
write_csv(reg_main, file.path(out_dir, "regression_main_hc3.csv"))

reg_fit <- data.frame(
  model = c("M1_base", "M2_extended"),
  n = c(m_base$n, m_ext$n),
  r2 = c(m_base$r2, m_ext$r2),
  adj_r2 = c(m_base$adj_r2, m_ext$adj_r2)
)
write_csv(reg_fit, file.path(out_dir, "regression_model_fit.csv"))

# -------------------- Robustness checks --------------------
# R1: Exclude zero-comment videos
sub_nonzero <- df[df$comment_count_effective > 0, ]
r1 <- hc3_lm(form_base, sub_nonzero)

# R2: Winsorize dependent variable (1%-99%)
df_w <- df
df_w$anger_rate_w <- winsorize(df_w$anger_rate, c(0.01, 0.99))
r2 <- hc3_lm(anger_rate_w ~ visual_main_arousal_label + text_arousal_label + log_comment_count, df_w)

# R3: Alternative DV: anger_mean_score
r3 <- hc3_lm(anger_mean_score ~ visual_main_arousal_label + text_arousal_label + log_comment_count, df)

# R4: Exclude small-sample videos (comment_count_effective < 10)
sub_ge10 <- df[df$comment_count_effective >= 10, ]
r4 <- hc3_lm(form_base, sub_ge10)

robust_tbl <- rbind(
  transform(r1$table, model = "R1_nonzero_comments"),
  transform(r2$table, model = "R2_winsorized_dv"),
  transform(r3$table, model = "R3_alt_dv_anger_mean_score"),
  transform(r4$table, model = "R4_comment_ge10")
)
robust_tbl <- robust_tbl[, c("model", "term", "estimate", "se_hc3", "t_value", "p_value", "ci_low", "ci_high")]
write_csv(robust_tbl, file.path(out_dir, "robustness_hc3.csv"))

robust_fit <- data.frame(
  model = c("R1_nonzero_comments", "R2_winsorized_dv", "R3_alt_dv_anger_mean_score", "R4_comment_ge10"),
  n = c(r1$n, r2$n, r3$n, r4$n),
  r2 = c(r1$r2, r2$r2, r3$r2, r4$r2),
  adj_r2 = c(r1$adj_r2, r2$adj_r2, r3$adj_r2, r4$adj_r2)
)
write_csv(robust_fit, file.path(out_dir, "robustness_model_fit.csv"))

# -------------------- Lightweight report --------------------
report_path <- file.path(out_dir, "advanced_analysis_report.md")

fmt_p <- function(p) {
  if (is.na(p)) return("NA")
  if (p < 1e-4) return("<0.0001")
  sprintf("%.4f", p)
}

line <- function(x) paste0(x, "\n")

cat(
  line("# 进阶统计分析（不使用 high_anger_flag）"),
  line(""),
  line(sprintf("- 样本量：%d", nrow(df))),
  line("- 因变量主设定：anger_rate"),
  line("- 核心自变量：visual_main_arousal_label + text_arousal_label"),
  line("- 控制变量：log_comment_count（以及扩展模型中的 visual_main_arousal_share / text_arousal_confidence）"),
  line(""),
  line("## 显著性检验"),
  line(sprintf("- Kruskal(visual): p=%s", fmt_p(kw_visual$p.value))),
  line(sprintf("- Kruskal(text): p=%s", fmt_p(kw_text$p.value))),
  line(sprintf("- ANOVA(visual): p=%s", fmt_p(as.numeric(anova_visual[1, "Pr(>F)"])))),
  line(sprintf("- ANOVA(text): p=%s", fmt_p(as.numeric(anova_text[1, "Pr(>F)"])))),
  line(sprintf("- Chi-square(visual x text): p=%s", fmt_p(chi_vt$p.value))),
  line(sprintf("- Spearman(comment_count_effective, anger_rate): rho=%.4f, p=%s", as.numeric(cor_spearman$estimate), fmt_p(cor_spearman$p.value))),
  line(""),
  line("## 回归与稳健性结果文件"),
  line("- regression_main_hc3.csv"),
  line("- regression_model_fit.csv"),
  line("- robustness_hc3.csv"),
  line("- robustness_model_fit.csv"),
  line("- significance_overview.csv"),
  line("- pairwise_wilcoxon_holm.csv"),
  file = report_path,
  sep = ""
)

cat("[OK] Advanced analysis done\n")
cat("[OK] Output dir:", out_dir, "\n")
cat("[OK] Report:", report_path, "\n")
