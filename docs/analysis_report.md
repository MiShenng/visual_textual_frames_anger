# 分析结果汇总

- 样本量: 461 条视频
- 字段数: 24 列

## 表1 样本描述统计
- 文件: analysis_tables/table1_numeric_descriptive.csv
- 文件: analysis_tables/table1_categorical_descriptive.csv

## 表2 文本与视觉框架分布
- 文本框架主导: 缓释 (269, 58.35%)
- 视觉框架主导: 缓释 (199, 43.17%)
- 文件: analysis_tables/table2_frame_distributions.csv

## 表3 列联与独立性检验
- 卡方统计量: 52.8568
- 自由度: 4
- p值: 9.13029e-11
- Cramer's V: 0.2394
- 文件: analysis_tables/table3_visual_text_crosstab.csv
- 文件: analysis_tables/table3_chi_square_meta.csv

## 表4 组合与愤怒表达
- 文件: analysis_tables/table4_anger_by_frame_combo.csv

## 回归表
- 模型: 负二项回归 (anger_count, offset=log(comment_count_effective))
- 文件: analysis_tables/regression_nb_coefficients.csv
- 文件: analysis_tables/regression_nb_fit.csv
