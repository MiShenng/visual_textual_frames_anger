# 进阶统计分析（不使用 high_anger_flag）

- 样本量：468
- 因变量主设定：anger_rate
- 核心自变量：visual_main_arousal_label + text_arousal_label
- 控制变量：log_comment_count（以及扩展模型中的 visual_main_arousal_share / text_arousal_confidence）

## 显著性检验
- Kruskal(visual): p=<0.0001
- Kruskal(text): p=0.0001
- ANOVA(visual): p=<0.0001
- ANOVA(text): p=0.0002
- Chi-square(visual x text): p=<0.0001
- Spearman(comment_count_effective, anger_rate): rho=0.5406, p=<0.0001

## 回归与稳健性结果文件
- regression_main_hc3.csv
- regression_model_fit.csv
- robustness_hc3.csv
- robustness_model_fit.csv
- significance_overview.csv
- pairwise_wilcoxon_holm.csv
