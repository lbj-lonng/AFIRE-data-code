# Afire Project v7：最终实验完整运行包（Linux，数据不随包提供）

本项目用于补齐并统一运行美国西部六州县级野火 PM₂.₅—COPD死亡—社会经济劣势研究的最终实验。

## 本版补齐的关键内容

1. 使用 Poisson 伪最大似然修复州×年份固定效应模型，避免原M3高维负二项IRLS不收敛。
2. 温度调整主模型和完全环境调整模型均补充“剔除2020年”版本。
3. 使用 `总PM₂.₅－野火来源PM₂.₅` 构造非野火PM₂.₅敏感性模型，并自动检查覆盖率、单位兼容性和负值比例。
4. 对主模型计算 SES=-2、-1、0、+1、+2 SD 时的正式边际效应与95%CI；边际效应使用主效应、交互项及二者协方差，并按30套插补进行Rubin合并。
5. 完成2009—2020逐年剔除分析。
6. 完成六州逐州剔除分析。
7. 完成六州州别分层探索性分析。
8. 完成六类次要疾病结局的温度调整模型。
9. 完成贫困率效应修饰、2009—2016和2017—2020分期分析。
10. 自动生成论文主表、敏感性表、森林图、边际效应图和最终运行报告。

## 必需数据

仅需从已经运行完成的 v6.3 项目复制两个文件：

```text
data_processed/county_year_disease_panel_v6_3.csv
data_processed/imputed_deaths_eb_history_v5.npz
```

不需要重新放置 NOAA、Census、CDC-Air、PLACES 或CDC WONDER原始文件，因为这些数据已经整合进分析面板。

## 推荐运行

```bash
bash setup_linux.sh
bash 01_validate_data_linux.sh
bash 02_quick_check_linux.sh
bash 03_run_final_missing_experiments_linux.sh
```

任务自动保存到：

```text
results/models/<MODEL_ID>/checkpoints/imputation_01.json
...
results/models/<MODEL_ID>/checkpoints/imputation_30.json
```

中断后重新执行相同命令即可续跑。

## 全部从头重跑

```bash
bash run_everything_from_scratch_linux.sh
```

## 主要输出

```text
results/tables/paper_main_and_key_sensitivity_v7.csv
results/tables/marginal_effects_v7.csv
results/tables/leave_one_year_out_v7.csv
results/tables/leave_one_state_out_v7.csv
results/tables/state_specific_v7.csv
results/tables/secondary_outcomes_v7.csv
results/tables/model_status_v7.csv
results/tables/final_check_v7.csv
results/figures/
results/reports/Afire_v7_final_experiment_report.md
```

## 研究边界

本项目完成的是当前论文的**县级年度长期生态面板实验**。它不等同于独立的短期事件因果研究。若论文仍要保留野火事件DiD、ITS或日级健康效应，需要另行提供事件边界、事件日期和日/周级健康结局数据。
