"""Write neutral legends, data notes and honest audit disclosures."""
from environment import ROOT,SUB,SD,AUD,PREV
from scope import CONFIG,IDS,LABELS
from docx import Document
from pathlib import Path
import json,hashlib,subprocess,sys,os,re
import pandas as pd

def put(path,text):path.write_text(text.strip()+'\n',encoding='utf-8')
def run():
    doc=Document(SUB/'Main_Text_CN_2009_2020_five_outcomes_clean.docx')
    put(SUB/'Figure_Legends_CN.md','\n\n'.join(doc.paragraphs[i].text for i in [14,20,25,30]))
    put(SUB/'Figure_Legends_EN.md',r'''# Main figure legends

Figure 1 | State-level smoke exposure, economic context and archived fire records. a, Mean annual wildfire PM2.5 for 49 state-level units during 2009–2020. The six study states have dark outlines. Alaska and Hawaii have missing exposure, not zero values; DC is enlarged separately. Insets use independent scales. b, Equal-state mean (solid), median (dashed) and 10th–90th percentiles (shading) for the same 12 years. Shading describes the distribution across states, not confidence intervals or national population-weighted exposure. c, A fixed baseline state poverty proxy, aggregated from county poverty proportions using county total population, versus mean exposure. All 49 points have equal area; orange identifies the six states. The true baseline is the ACS 2006–2010 five-year period; it is distinct from the county disadvantage index used in mortality models. No regression, correlation test or confidence band is added. d, The 81 records dated 2009–2020 in an existing archived Top100 catalogue yield 89 state–record assignments. The six study states account for 55 assignments involving 53 distinct catalogue records. Cross-state and potential duplicate records are retained. This subset is not a newly ranked national Top100 for the study period, and catalogue records are not necessarily independent fires. Original extraction and ranking/deduplication provenance remains incomplete (Supplementary Tables S20–S22). Source data are provided.

Figure 2 | County-level smoke exposure and its socioeconomic distribution. a, Mean annual wildfire PM2.5 during 2009–2020 for all 256 counties in the six study states, shown using Census 2020 boundaries and EPSG:5070. All county FIPS match exactly; grey denotes non-study states. b, Annual county-population-weighted mean (solid), equal-county median (dashed) and 10th–90th percentiles (shading), 2009–2020. Shading is the across-county distribution, not a confidence interval. c, Annual equal-county Gini for the same 256 counties. d, Twelve-year county means by fixed disadvantage quintile, containing 52, 51, 51, 51 and 51 counties from low to high disadvantage. Boxes span the interquartile range, centre lines show medians, whiskers extend to the most extreme observations within 1.5 interquartile ranges, and diamonds show means. All county points, including those outside whiskers, are retained; deterministic horizontal jitter does not change exposure values. State poverty and county disadvantage are different measures. Source data are provided.

Figure 3 | County mortality suppression and evidence for state-total-constrained allocation. a, Percentage of original Suppressed records during 2009–2020: 60 county–year–cause records per county (12 years × five causes), across 256 counties. This is not the fraction of deaths imputed. b, Suppressed records as a percentage of each cause's 3,072 records (blue), and hidden state remainders as a percentage of the corresponding state death totals (orange). The two columns have different denominators and different zero-origin axis ranges; nested causes must not be summed. c,d, Mean absolute error and empirical coverage of nominal 95% allocation intervals for equal, population-weighted, fixed empirical Bayes (EB) and hierarchical EB methods. All methods use the same 298 groups and 2,128 publicly observed 10–19-count cells in the five-cause, 2009–2020 evaluation subset. Results aggregate existing per-cell predictions from 100 allocations per method with support 0–19; filtering the evaluation set does not retrain the historical weights. The dashed line in d marks 95%; no new uncertainty bars are estimated. This validation differs from the primary 30-allocation, 1–9 implementation and does not calibrate mortality-model confidence intervals. Full metrics are in Supplementary Table S13 and Source Data.

Figure 4 | Socioeconomic modification and same-sample environmental adjustment. a, Fixed baseline county disadvantage in cross-county standard-deviation units; higher values indicate greater disadvantage. The actual baseline is 2006–2010. This is not a map of county-specific mortality effects. b, Percentage change in the ratio of rate ratios (RRR) per smoke IQR and per one-SD increase in disadvantage. c, Conditional smoke associations per IQR at disadvantage 0, +1 and +2 SD, encoded by circles, squares and diamonds and by blue, green and orange. Panels b and c have different estimands and use 3,072 county–years, 256 counties and 30 existing imputations. d, Common-sample M2 (grey circles) versus M3PL_joint (orange diamonds), which jointly adds non-wildfire PM2.5, ozone, precipitation and relaxed-QA daytime land-surface temperature. Both models use exactly the same 3,062 county–years and all 30 allocation vectors. Points and horizontal lines are saved pooled estimates and ordinary two-sided 95% confidence intervals, not intervals for between-model differences. COPD, CLRD, RESP, CIRC and IHD denote chronic obstructive pulmonary disease, chronic lower respiratory diseases, respiratory system diseases, circulatory system diseases and ischaemic heart disease, respectively. The study window is 2009–2020; reporting five causes retains the original seven-test Holm adjustment family described in Methods. Supplementary Tables S5–S9 report all retained conditional and sensitivity results. Source data are provided.''')
    put(SD/'README.md','''# Source Data: 2009–2020, five outcomes

Study window: 2009–2020 (12 years). Outcome order: COPD, CLRD, RESP, CIRC, IHD. The corresponding IDs and unchanged ICD definitions are in full_results/outcome_dictionary.csv. Parent categories retain their full original definitions and must not be summed into unique deaths.

Figure_1 through Figure_4 contain each panel's underlying records. full_results contains the 135 unchanged health-result rows (A 5, B 25, C 40, D 25, E 40), all ordinary intervals and saved P values; no new fit, allocation or inference was performed. Table_S*.csv mirror the current supplementary tables; health_results.csv holds unrounded estimates. S13 tables include the five-cause pool and all five cause-specific validation summaries. All pooled metrics are cell-weighted, not simple averages of disease summaries.

Model metadata fields such as run_source, elapsed_seconds, task_id and run_fingerprint describe the archived original fitting run. In particular, a saved run_source value of recomputed does not mean that the model was refitted during this reporting revision. Original numeric metadata is retained for traceability.

mortality_records.csv contains 15,360 selected original aggregate records and suppression flags; public zero is 0, Suppressed is not zero, and hidden individual counts are not exposed. state_death_remainders.csv contains 360 state–year–cause groups and observed hidden remainders. validation_evaluation_records.csv contains 8,512 method–cell rows (four methods × 2,128 common cells), never new predictions. county_year_exposure.csv has 3,072 unique county–years; state_year_exposure.csv has 588 observed state–years. state_year_exposure_with_missing.csv includes the 24 missing AK/HI rows; absence is not zero.

Concentrations are annual wildfire PM2.5 in micrograms per cubic metre. Mean exposure uses equal years; regional means use current-year county population; medians, percentiles and Gini use equal counties or states as labelled. ses is the frozen cross-county SD-scaled disadvantage measure. Its actual baseline, and the state poverty proxy baseline, are 2006–2010. Historical allocation/validation training information was not relabelled or regenerated. The fixed smoke IQR is 0.678107947271523 micrograms per cubic metre.

Five-cause reporting retains the original Holm family size 7. P_adjusted is the saved adjusted value, not a five-test recalculation; ordinary 95% intervals are not simultaneous intervals. Conditional estimates may be negative or cross zero. Common-sample model identities are in common_sample_identity.csv. Nested-outcome diagnostics describe existing arrays, not joint posterior violation probabilities.

fire_catalogue_subset.csv retains 81 original records dated 2009–2020, with original Rank and identifiers. fire_record_state_assignments.csv has 89 assignments; cross-state and potential duplicates are retained. This is a subset of an archived list, not a newly ranked national Top100. geography contains the original supplied Census boundary files and derived drawing geometry. No scientific values were spatially interpolated or reallocated.

CSV uses UTF-8, decimal point '.', empty fields for unavailable/not applicable values, and string FIPS identifiers (state two digits; county five digits). Read identifier columns as strings. Hashes and historical input paths are retained only in the internal audit directory. Public repository identifier, authors, original CDC query archive, some upstream product versions and redistribution permissions remain unresolved. Local availability does not establish permission to publish third-party inputs; obtain these before public deposition.''')
    put(AUD/'SCOPE_CHANGE_LOG.md',f'''# 范围统一变更记录

实际使用最近完整稿：{PREV}，主文来自05_manuscripts/Main_Text_CN_clean.docx，SI及四图来源与其匹配。没有退回早期稿。未发现适用AGENTS.md；已检查工作目录及D:/、postgraduate、wildfire、9.10、9.15各级。

观察期统一2009—2020年，五类结局固定顺序与ICD未改变。正式Submission与历史Audit分离；原始文件不删除不覆盖。脚本统一配置scope_config.yaml为JSON语法的合法YAML，无额外YAML运行依赖。

重新汇总：588州—年、3,072县—年、15,360死亡记录、3,328受抑制记录、325公开零值、360州死亡组、每县60条分母、72跨尺度对比；各死因实际余量及比例；四方法2,128共同验证单元/298组的MAE、RMSE、覆盖率、宽度、CRPS和区间评分；81条目录记录/89次归属/六州55次及53条不同记录；五类25项条件对比分类；三类嵌套关系计数。

直接复用并核验：2009—2020年县均值、固定劣势五分位、描述性相关、州均值、135行健康估计、普通CI、原始P与已存Holm P、3,062共同样本、固定IQR/SES、30份已有1—9分配、所有既有模型公式与推断身份。没有重新插补、拟合、标准化或新增P/CI/bootstrap。

校正不是五项Holm：真实原家族大小7，仅收窄报告范围。公开父类ICD和计数没有扣除任何组成诊断。保留五类自身负向条件关联、跨零CI、删样本和严格LST不利结果、验证适用边界及嵌套违反。真实基线/训练/产品/文献年份没有机械替换。

新验证排序：固定EB MAE 1.971983、层级EB 1.960028；固定EB CRPS 1.391503、层级EB 1.400846。不同指标并非同一方法全优，正文不作方法最优或重新校准主健康模型的主张。

旧观察范围的历史COPD O01行不再进入正式SI，原行保留内部输入。研究期内部的既有删年/删州敏感性保留其真实子时期。表S5—S9恰好135行。全部旧媒体关系已清理，Word不携带未使用的旧图。''')
    put(AUD/'statistical_adjustment_provenance.md','''# 原多重校正口径

本轮仅改变报告范围。原权威健康表被冻结于inputs/tables/AFIRE_7outcome_all_results.csv；五类A参考交互的beta、SE、双侧P、P_adjusted及普通CI逐值与其一致。当前配置original_holm_family_size = 7；不重算五项家族。内部原始清单保持完整以追溯被缩减的展示，正式Methods明确实际7项且未作前瞻性预注册。源字段comparison_family的旧报告范围别名改为original_Holm_family_n7，不改任何数值或真实家族。

模型单位为县—年，县为聚类单位；30份插补不是30个独立研究重复。固定EB、1—9计数支持、公开零/正计数保留、负二项、县/年份固定效应、人口offset、固定IQR与SES、县聚类有限样本修正、传统Rubin自由度均不变。所有B—E是既有解释性/敏感性结果，普通区间不是家族校正同时区间。并未以重叠区间检验模型差异。

图4d五类配对均为3,062县—年；实际row_id、键及顺序、30份拟合身份、实际分配数组sha256一致。3,072参考样本没有被当作共同样本。实际数组只按列筛选、计数和哈希检查，未生成或修复任何计数。

验证仅筛选已存逐单元记录。不同方法的2,128评价键相同，298组；原训练窗口、100次分配、0—19支持与主30份1—9数组不同。指标重汇总不等于独立训练验证，不生成新显著性或bootstrap区间。

保留五类25条件对比中15项普通区间全负、10项跨零、0项全正；0/+1/+2三个主图水平共15点。不能由正交互推断弱势县额外死亡或保护效应。''')
    put(AUD/'unresolved_items.md','''# 尚缺资料与未运行项目

本轮范围重算所需逐单元验证、死亡记录和已有模型均已找到；没有以旧指标冒充当前子集，没有待补数据占位的主图面板。

投稿来源状态仍为PARTIAL，需要作者补充：

1. 归档重大火灾目录的原获取日期、边界/点位版本、查询、全库Rank生成和事件去重脚本。已有81条子集不能认证该时期全国最大独立火灾集合。
2. 县级综合劣势指数的上游全部组成、权重、缺失处理及精确NHGIS/ACS提取档案；州级贫困代理不能替代该指数。
3. 本批CDC WONDER县/州原始查询、下载批次及再分发许可；部分年龄、密度、干旱、气温、降水、背景污染精确输入版本/单位及聚合链。
4. 作者、单位、通讯作者、贡献、资助、利益冲突和机构伦理认定；公共数据/代码仓库永久标识及许可。

保留的解释限制：固定基线与随访前两年重叠；历史权重和验证不是仅用当前观察期重训；跨县残余相关未自动处理；三个保留父子关系仍有数组不一致，联合重建对估计的影响未评估；负向/跨零条件关联及删样本区间不利结果不可隐藏。

NOT_RUN（按本轮禁止事项不运行）：死亡模型重新拟合、重新插补、Gamma–Poisson重训、SES/IQR重标准化、新Holm/显著性/CI/bootstrap、全国火灾全库下载重排名。未另行编译LaTeX PDF；原生OMML和独立equations.tex已交付。文献多来源元数据沿用同日冻结核验，本轮仅复查使用范围、编号、题名和年份。''')
    put(ROOT/'README.md',f'''# AFIRE：2009—2020年、五类心肺死因修订版

正式交付在submission/，历史来源与核验在audit/。以最近完整稿{PREV.name}为起点，不覆盖任何旧稿或实验。四张主图均保留a—d结构；两Results、四Methods、独立Conclusion保持。Word有干净版、讨论每段一个完整重点句标黄版、完整补充信息；另有中英文图注、PDF/SVG/600dpi PNG四主图、七张补充图、135行完整健康结果、逐面板Source Data和可编辑公式源码。

本轮完成报告在FINAL_REPORT.md，最终文件哈希清单在audit/DELIVERY_MANIFEST.csv，实际视觉检查记录在audit/visual_review.csv。

观察期2009—2020年、12年；COPD/CLRD/RESP/CIRC/IHD五类。真实基线和历史训练年份保留。已重新汇总所有范围依赖的描述统计和验证子集，不重新拟合、插补或推断；原7项Holm家族不缩小。模型和图4d配对原值保持。

当前来源/投稿条件仍PARTIAL，详见audit/unresolved_items.md；这不表示主要面板缺少当前范围数据。本地资料不等于已获得公开再分发许可。

## 一条重建命令（PowerShell）

```powershell
& 'C:\\Users\\86189\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' '{ROOT}\\scripts\\run_all.py'
```

重建入口仅读冻结记录和既有数组，重建本版本描述汇总、图、Word及程序核验。渲染使用已缓存的任务专用portable LibreOffice，不控制桌面Word/LibreOffice。配置和依赖见scripts/environment.py及audit/runtime_versions.json。视觉通过记录绑定最终PNG哈希；若重建改变页面，应重新视觉检查。
''')
    # Run the installed scientific-figure source preflight; retain raw warnings.
    report=[]
    for p in [*sorted((ROOT/'scripts').glob('plot_figure_*.py')),ROOT/'scripts/plot_supplement.py']:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/qa_helpers/validate_figure.py'),str(p),'--json'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        put(AUD/'skill_validation'/(p.stem+'.json'),r.stdout or r.stderr);report.append({'source':p.name,'returncode':r.returncode,'note':'shared style imported; actual dimensions/fonts/vector paths separately verified'})
    put(AUD/'skill_validation/summary.json',json.dumps(report,indent=2))
    # Provenance map links every delivered CSV to a concrete generation step.
    mapping=[]
    for p in sorted(SD.rglob('*.csv')):
        n=p.name;script='finalize.py' if n.startswith('Table_') or n in ['model_formulas.csv','county_geographic_join.csv'] else 'audit_allocations.py' if n in ['nested_outcome_check.csv','common_sample_identity.csv'] else 'plot_supplement.py' if n.startswith('Supplementary_Figure') else 'plot_figure_'+p.parent.name.split('_')[-1]+'.py' if p.parent.name.startswith('Figure_') else 'prepare_scope_data.py'
        mapping.append({'delivered_file':str(p.relative_to(ROOT)),'builder':script,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'upstream':'See builder paths and audit/INPUT_MANIFEST.csv; original model results retained unchanged'})
    pd.DataFrame(mapping).to_csv(AUD/'source_data_provenance.csv',index=False)
    print('Legends, data notes, scope log, provenance and unresolved items saved.')
if __name__=='__main__':run()
