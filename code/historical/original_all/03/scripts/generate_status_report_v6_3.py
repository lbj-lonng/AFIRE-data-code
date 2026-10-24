from __future__ import annotations
import json, os
from pathlib import Path
import pandas as pd
ROOT=Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT',Path(__file__).resolve().parents[1])); TABLES=ROOT/'tables'; REPORTS=ROOT/'reports'; LOGS=ROOT/'logs'; REPORTS.mkdir(exist_ok=True)
coverage=pd.read_csv(TABLES/'integrated_data_coverage_v6_3.csv') if (TABLES/'integrated_data_coverage_v6_3.csv').exists() else pd.DataFrame()
screen=pd.read_csv(TABLES/'screening_models_mean_mi_v6_3.csv') if (TABLES/'screening_models_mean_mi_v6_3.csv').exists() else pd.DataFrame()
status=pd.read_csv(TABLES/'screening_model_status_v6_3.csv') if (TABLES/'screening_model_status_v6_3.csv').exists() else pd.DataFrame()
full=pd.read_csv(TABLES/'pooled_available_models_v6_3.csv') if (TABLES/'pooled_available_models_v6_3.csv').exists() else pd.DataFrame()
lines=['# Afire v6.3 数据整合、模型状态与实施说明','', '## 一、已经直接包含并通过检查的数据','', '- CDC WONDER 六州县级和州级死亡数据，2006—2020年。','- 州总量约束的30套Suppressed多重插补结果。','- 县级野火来源PM₂.₅数据。','- NHGIS社会经济数据；主模型使用2006—2010固定基线SES，时变SES仅用于2010—2020敏感性分析。','- Census ACS 2009—2020及2020 Gazetteer土地面积；无需再次申请Census密钥。','- 用户提供的NOAA D0—D4月度文件，严格作为干旱分类面积比例使用。','- 用户提供的CDC/EPA PM₂.₅与臭氧文件，仅覆盖ID、OR、WA，严格作为三州敏感性分析。','']
lines+=['## 二、数据覆盖率','']
if not coverage.empty:
    lines.append('|变量|年份|覆盖率|县数|六州主模型可用|')
    lines.append('|---|---:|---:|---:|---|')
    for _,r in coverage.iterrows():
        lines.append(f"|{r['variable']}|{int(r['year_min'])}—{int(r['year_max'])}|{r['coverage_pct']:.2f}%|{int(r['counties_with_data'])}|{'是' if bool(r['six_state_main_model_eligible']) else '否'}|")
lines+=['','## 三、当前已预计算的快速筛查结果','', '以下结果使用30套插补死亡数的逐单元均值进行一次负二项回归，用于检查方向和代码，不替代最终Rubin合并推断。','']
if not screen.empty:
    inter=screen[screen['term'].astype(str).str.contains(':',regex=False)].copy()
    lines.append('|模型|交互变化|95%CI|p值|范围|')
    lines.append('|---|---:|---:|---:|---|')
    for _,r in inter.iterrows():
        lines.append(f"|{r['specification']}|{r['percent_change']:.3f}%|{r['percent_change_ci_low']:.3f}% 至 {r['percent_change_ci_high']:.3f}%|{r['p_value']:.4g}|{r['states_included']}|")
if not status.empty:
    pending=status.loc[~status['status'].eq('completed')]
    if not pending.empty:
        lines+=['','未预计算完成的筛查模型会在Linux完整流程中继续运行：']
        for _,r in pending.iterrows(): lines.append(f"- {r['specification']}：{r.get('reason','未完成')}")
lines+=['','## 四、如何运行','', '### 1. 建立Linux环境','', '```bash','unzip Afire_project_v6_3_integrated_linux_complete.zip','cd Afire_project_v6_3_integrated_linux','bash setup_linux.sh','```','', '### 2. 快速检查','', '```bash','bash run_quick_check_linux.sh','```','', '### 3. 完整30套多重插补模型','', '```bash','bash run_full_linux.sh','```','', '脚本按模型保存检查点。中断后重新运行会跳过已经完成的模型。','', '### 4. 下载仍缺少的官方数据','', '```bash','bash download_missing_official_linux.sh','```','', '该步骤只更新真实NOAA温度/降水、六州CDC/EPA空气污染和PLACES吸烟率。Census已经随包提供，不需要API密钥。','', '## 五、解释边界','', '- D0—D4不能解释为温度。','- 三州CDC-Air结果不能外推为六州结果。','- 快速筛查不是最终多重插补推断。','- 完整模型结果应读取 `tables/pooled_available_models_v6_3.csv`。','- 剔除2020年后效应减弱时，应将结论定位为极端烟雾年份驱动的探索性信号。']
(REPORTS/'实施结果与后续运行说明_v6_3.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(REPORTS/'实施结果与后续运行说明_v6_3.md')
