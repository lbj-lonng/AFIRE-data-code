# Afire Project v5：州总量约束多重插补优化

## 范围

Arizona、California、Colorado、Idaho、Oregon和Washington，共256个县、2006—2020年、7类疾病。

## 方法升级

- 每个Suppressed县—年死亡数限制在0—9例。
- 每个州—年—疾病的县级死亡数严格等于州级CDC WONDER总死亡数。
- 主分析生成30套条件泊松多重插补数据，并用Rubin规则合并模型。
- 人口权重和等权插补用于检验历史疾病率权重依赖。

## 一键运行

Linux：`bash run_all.sh`

Windows：`run_all.bat`

也可执行：`python scripts/run_all.py`

## 关键输出

- `reports/州总量约束多重插补优化结果报告_v5.docx`
- `tables/state_county_reconciliation_v5.csv`
- `tables/pooled_multiple_imputation_models_v5.csv`
- `tables/mi_vs_complete_case_comparison_v5.csv`
- `tables/county_disease_screening_priority_mi_v5.csv`
- `data_processed/county_year_disease_panel_v5.csv`
- `data_processed/suppressed_deaths_mi_draws_v5.csv.gz`
- `figures/Fig1-Fig8`

## 注意

插补值不是实际死亡数；结果为县尺度生态学证据。
