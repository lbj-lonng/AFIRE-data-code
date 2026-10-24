# Afire v2 论文优化结果与下一步

## 1. 现在是否需要重跑

结论：**不需要全量重跑**。

本次完整性检查确认关键表、关键字段、2006–2020 年、7 个疾病类别、Top100–PM2.5 overlap 定义、WPHII v2 公式和疾病模型均完整。当前应直接使用已有结果进行论文写作。只有更换原始数据、修正暴露聚合、改变 Top100 火灾表或发现源数据错误时，才需要运行全流程。

## 2. 只写论文时优先查看

- `reports/最终论文分析报告_v2.docx`：完整论文式结果稿、局限性和答辩问答。
- `reports/论文结果解读与修改建议_v2.docx`：哪些结果可主写、哪些必须谨慎解释。
- `reports/论文主线_v2.docx` / `.md`：结果章节逻辑。
- `figures_paper_v2/Fig1_v2_...` 至 `Fig8_v2_...`：论文和答辩图。
- `tables/fire_cover_vs_noncover_summary_v2.csv`：统一的 cover 对照表。
- `tables/WPHII_top10_comparison_v2.csv`：不同权重 Top10 稳定性。

## 3. 主结果与补充结果

**主结果**：年度暴露均值与不公平性趋势；Top100–PM2.5 overlap 的年份和州分布；分疾病健康负担不公平性；WPHII v2 排名与权重稳定性。

**补充结果**：同期疾病模型；1 年滞后率模型和 population-offset 死亡数模型；fire-covered vs non-covered 的未调整健康率比较。

## 4. 不得过度解释

- 州尺度结果不是个体因果效应。
- 负向健康系数不是保护作用。
- Top100 不是全部火灾。
- PM2.5 cover 是高烟雾暴露覆盖，不等于燃烧面积或单场火灾烟羽。
- WPHII 是综合优先级指数，不是归因风险或效应估计。
- cover 组与 non-cover 组 PM2.5 差异部分由定义决定。

## 5. 只重新生成论文优化结果

在项目根目录运行：

```bash
python scripts/11_paper_optimization_v2.py
```

该命令直接读取 `data_processed` 和 `tables`，不依赖原始数据目录。

## 6. 需要全量重跑时

Windows PowerShell：

```powershell
cd D:\postgraduate\wildfire\Afire\Afire_project_v2
$env:AFIRE_DATA_ROOT = "D:\postgraduate\wildfire\Afire"
python scripts\run_all.py
python scripts\11_paper_optimization_v2.py
```

Windows CMD：

```bat
cd /d D:\postgraduate\wildfire\Afire\Afire_project_v2
set AFIRE_DATA_ROOT=D:\postgraduate\wildfire\Afire
python scripts\run_all.py
python scripts\11_paper_optimization_v2.py
```

Linux：

```bash
cd /path/to/Afire_project_v2
export AFIRE_DATA_ROOT=/path/to/Afire
python scripts/run_all.py
python scripts/11_paper_optimization_v2.py
```

`AFIRE_DATA_ROOT` 必须指向同时包含 `PM2.5`、`health`、`fire` 和 `ecnomy` 子目录的原始数据根目录。

## 7. 输出清单

新增输出包括 lag1 模型、WPHII 敏感性、fire-cover 对照表、8 幅 PNG/PDF 论文图、4 份专题 Word 报告、最终论文分析报告和本说明文件。
