# Afire Project v6.3：已整合真实数据的 Linux 完整版

## 项目定位

本项目研究2006—2020年美国西部六州县尺度野火烟雾PM₂.₅、社会经济脆弱性与COPD死亡负担的关系。

v6.3在v5州总量约束多重插补基础上，已经把用户下载并通过检查的数据直接加入项目，不再要求手工复制Census文件。

## 已直接包含的数据

1. CDC WONDER六州县级和州级死亡数据；
2. 30套州总量约束Suppressed多重插补；
3. 县级野火来源PM₂.₅；
4. NHGIS社会经济数据；
5. Census ACS 2009—2020和2020 Gazetteer土地面积；
6. NOAA D0—D4月度干旱分类文件；
7. CDC/EPA Downscaler PM₂.₅和臭氧的现有三州数据。

### 重要数据边界

- Census已完整覆盖256个县×12个ACS版本，共3,072条记录，`age65_share`和`population_density_km2`覆盖率100%。
- NOAA D0—D4是干旱分类面积比例，不是温度。项目只把它们作为干旱敏感性变量。
- 当前CDC-Air只覆盖ID、OR、WA三州，不能进入六州主模型，只进入三州敏感性分析。
- 吸烟率尚未随用户数据包提供，只能在下载真实PLACES数据后运行短时期敏感性模型。

## 方法修正

- 主SES修饰变量改为固定的2006—2010基线SES；
- 时变SES严格按ACS窗口结束年份对应，只用于2010—2020敏感性分析；
- 不再把`2006_2010`错误标记为2006年单年数据；
- 健康模型人口offset继续使用CDC WONDER人口；
- Census人口只用于老龄化比例和人口密度；
- 三州空气污染结果不会被表述为六州结果。

## Linux运行

### 1. 解压并进入项目

```bash
unzip Afire_project_v6_3_integrated_linux_complete.zip
cd Afire_project_v6_3_integrated_linux
```

### 2. 创建环境

```bash
bash setup_linux.sh
```

### 3. 快速检查

```bash
bash run_quick_check_linux.sh
```

快速检查使用30套插补死亡数的逐单元均值进行一次负二项回归，用于检查数据、代码和结果方向，不替代最终Rubin合并推断。

### 4. 正式完整运行

```bash
bash run_full_linux.sh
```

正式流程将：

- 对每套插补数据分别运行负二项固定效应模型；
- 使用县聚类稳健标准误；
- 用Rubin规则合并30套结果；
- 按模型单独保存检查点；
- 中断后重新运行时跳过已完成模型。

### 5. 补齐仍缺失的官方数据

```bash
bash download_missing_official_linux.sh
```

该脚本会尝试从官方接口更新：

- NOAA县级年均及火灾季气温；
- NOAA降水；
- 六州CDC/EPA总PM₂.₅；
- 六州CDC/EPA臭氧；
- CDC PLACES吸烟率。

Census数据已经包含在包内，因此不需要Census API密钥。

## 主要输出

- `data_external/processed/census_county_year_six_states_2009_2020.csv`
- `data_external/processed/county_year_drought_categories_v6_3.csv`
- `data_external/processed/county_year_real_covariates_v6_3.csv`
- `data_processed/county_year_disease_panel_v6_3.csv`
- `tables/integrated_data_coverage_v6_3.csv`
- `tables/screening_models_mean_mi_v6_3.csv`
- `tables/pooled_available_models_v6_3.csv`（完整运行后）
- `reports/实施结果与后续运行说明_v6_3.md`

## 模型结构

- M1：固定基线SES，2006—2020；
- M2：加入真实Census老龄化和人口密度，2009—2020；
- M3：县固定效应＋州×年份固定效应；
- M4：加入真实干旱分类指标；
- M5：剔除2020年；
- M6：正确对应的时变SES；
- M7：lag1；
- M8：lead1未来暴露安慰剂；
- M9：ID/OR/WA三州总PM₂.₅和臭氧敏感性。

## 解释原则

- 快速筛查结果不是最终多重插补推断；
- 插补死亡数是符合约束的可能值，不是真实观测值；
- 县级年度生态学结果不能解释为个体因果效应；
- 剔除2020年后效应减弱时，应强调极端烟雾年份驱动；
- 三州空气污染模型只作为区域敏感性证据。
