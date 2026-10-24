"""Publish bilingual display tables from frozen values, without estimation.

prepare_tables() returns 22 ordered dictionaries for the document builder.
All numeric display strings are inherited from the current baseline tables;
the diagnostics/model-definition tables are reorganized from saved fields.
"""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'scripts/scope_config.yaml').read_text(encoding='utf-8'))
BASE = Path(CONFIG['base'])
OLD = BASE / 'submission/source_data/full_results'
OUT = ROOT / 'submission/source_data/tables'
IDS = CONFIG['outcomes']
LABELS = CONFIG['labels']
HISTORICAL = Path('C:/Users/86189/Documents/Codex/2026-09-10/ban/work/sources/AFIRE_B1_joint_adjustment_20260909_233833/AFIRE_B1_joint_adjustment_20260909_233833/04_tables/primary_B1_results.csv')


def load(name):
    with (OLD / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.reader(f))


def records(name):
    with (OLD / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerows(rows)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


WORDS = {
    '慢性阻塞性肺疾病': 'Chronic obstructive pulmonary disease',
    '慢性下呼吸道疾病': 'Chronic lower respiratory diseases',
    '呼吸系统疾病': 'Respiratory-system diseases',
    '循环系统疾病': 'Circulatory-system diseases',
    '缺血性心脏病': 'Ischaemic heart disease',
    '五类合并': 'Five-outcome pool', '等权': 'Equal weights', '人口权重': 'Population weights',
    '固定EB': 'Fixed EB', '层级EB': 'Hierarchical EB',
    '固定主要方案': 'Primary fixed EB', '历史层级方案': 'Historical hierarchical EB',
    '完整': 'Full sample', '删除2020': 'Omit 2020', '删除CA': 'Omit CA',
    '同时删除': 'Omit CA and 2020', '仅删除CA×2020': 'Omit CA in 2020',
    'CA × 其他年份': 'CA × other years', '其他五州 × 2020': 'Other states × 2020',
    '其他五州 × 其他年份': 'Other states × other years', '是': 'Yes', '否': 'No'
}


def english(value):
    value = WORDS.get(value, value)
    value = value.replace(' 至 ', ' to ')
    if re.search(r'[\u3400-\u9fff]', value):
        raise ValueError('Untranslated English table value: ' + value)
    return value


TITLES = {
 1: ('五类死亡结局及ICD-10范围', 'Mortality outcomes and ICD-10 definitions'),
 2: ('分析变量、变换及资料来源', 'Analytical variables, transformations and sources'),
 3: ('有观测州级单位的年度暴露分布', 'Annual exposure distributions across observed jurisdictions'),
 4: ('六州县级长期暴露分布', 'Within-state distributions of county long-term exposure'),
 5: ('六州区域年度暴露及县际分布', 'Annual regional exposure and between-county distributions'),
 6: ('固定劣势五分组中的县级长期暴露', 'County long-term exposure by fixed disadvantage quintile'),
 7: ('归档火灾记录的州归属', 'State assignments of archived fire-catalogue records'),
 8: ('死亡抑制记录、公开零值及州总量余量', 'Suppressed mortality records, public zeros and state remainders'),
 9: ('伪抑制验证的误差与概率评分', 'Errors and probabilistic scores in pseudo-suppression validation'),
 10: ('伪抑制验证的区间表现', 'Interval performance in pseudo-suppression validation'),
 11: ('历史COPD固定和层级分配的关联比较', 'Historical COPD associations under fixed and hierarchical allocation'),
 12: ('跨结局包含关系的数组诊断', 'Array diagnostics for nested-outcome relationships'),
 13: ('参考模型的插补诊断、离散度和分配种子', 'Reference-model imputation diagnostics, dispersion and allocation seeds'),
 14: ('共同样本的八个环境模型定义', 'Definitions of the eight common-sample environmental models'),
 15: ('五类结局的参考交互及原Holm校正', 'Reference interactions and saved Holm adjustment for five outcomes'),
 16: ('五类结局的完整条件烟雾关联', 'Complete conditional smoke associations for five outcomes'),
 17: ('共同样本的环境调整交互结果', 'Environmentally adjusted interactions in the common sample'),
 18: ('定向删样本交互结果', 'Interaction estimates under targeted sample omissions'),
 19: ('严格和宽松LST的配对交互结果', 'Paired interaction estimates under strict and relaxed LST criteria'),
 20: ('交互设计对比的地域与年份集中性', 'Geographical and temporal concentration of interaction design contrast'),
 21: ('历史COPD额外模型', 'Additional historical COPD models'),
 22: ('共同样本参考与联合模型的配对身份', 'Paired identity of common-sample reference and joint models')
}

HEADERS = {
 1: ['Abbreviation', 'Outcome', 'ICD-10'],
 3: ['Year', 'Jurisdictions', 'Mean', 'Median', 'P10', 'P90'],
 4: ['State', 'Counties', 'Mean', 'Median', 'P10', 'P90', 'Minimum', 'Maximum'],
 5: ['Year', 'Population-weighted mean', 'County median', 'P10', 'P90', 'Gini'],
 6: ['Disadvantage quintile', 'Counties', 'Mean', 'Median', 'Minimum', 'Maximum'],
 7: ['State', 'Code', 'Record assignments', 'Six-state region'],
 8: ['Outcome', 'Suppressed records', 'Public zeros', 'Hidden remainder', 'Suppressed records (%)', 'Hidden deaths (%)'],
 9: ['Scope', 'Method', 'MAE', 'RMSE', 'CRPS'],
 10: ['Scope', 'Method', 'Coverage (%)', 'Interval width', 'Interval score'],
 11: ['Allocation scheme', 'Allocations', 'Interaction (%)', 'Ordinary 95% CI'],
 12: ['Exceedance', 'Draw-wise', 'Any draw', 'Mean count', 'Public n / violations', 'Maximum excess'],
 15: ['Outcome', 'Model', 'County-years', 'Interaction (%)', 'Ordinary 95% CI', 'Unadjusted P', 'Original 7-test Holm P'],
 16: ['Outcome', 'Disadvantage', 'County-years', 'Conditional change (%)', 'Ordinary 95% CI', 'Unadjusted P'],
 17: ['Outcome', 'Model', 'County-years', 'Interaction (%)', 'Ordinary 95% CI', 'Unadjusted P'],
 18: ['Outcome', 'Omission', 'County-years', 'Interaction (%)', 'Ordinary 95% CI', 'Unadjusted P'],
 19: ['Outcome', 'LST pair', 'County-years', 'Interaction (%)', 'Ordinary 95% CI', 'Unadjusted P'],
 20: ['Geography × year', 'Records', 'Record share (%)', 'Residual SS share (%)'],
 21: ['Model', 'Years', 'County-years', 'Interaction (%)', 'Ordinary 95% CI', 'Unadjusted P'],
 22: ['Outcome', 'Reference', 'Joint', 'County-years', 'Counties', 'Allocations', 'Keys / counts match']
}

SOURCES = {
 1: ['outcome_dictionary.csv'], 2: [], 3: ['state_annual.csv', 'state_year_exposure.csv'],
 4: ['within_state_county_distribution.csv', 'county_map_values.csv'],
 5: ['annual.csv', 'county_year_exposure.csv'], 6: ['quintiles.csv', 'county_map_values.csv'],
 7: ['fire_state_counts.csv', 'fire_record_state_assignments.csv'],
 8: ['suppression.csv', 'state_death_remainders.csv'],
 9: ['validation.csv', 'validation_evaluation_records.csv'],
 10: ['validation.csv', 'validation_evaluation_records.csv'],
 11: ['primary.csv'], 12: ['nested_outcome_check.csv'], 13: ['primary.csv', 'model_diagnostics.csv'],
 14: ['model_formulas.csv'], 15: ['primary.csv'], 16: ['conditional.csv'],
 17: ['common_sample.csv'], 18: ['targeted_omissions.csv'], 19: ['LST_pairs.csv'],
 20: ['design.csv'], 21: [], 22: ['common_sample_identity.csv']
}

BASE_EFFECT_CN = '单位为每固定IQR烟雾（0.678107947271523 μg/m³）及每1 SD县级劣势的100×(RRR−1)。区间为普通双侧95% CI；n为县—年，不是分配份数。数值显示舍入，完整精度见配套Source Data。'
BASE_EFFECT_EN = 'Effects are 100×(RRR−1) per fixed smoke IQR (0.678107947271523 μg/m³) and 1 SD county disadvantage. Intervals are ordinary two-sided 95% CIs; n denotes county-years, not allocations. Display rounding does not alter the full-precision Source Data.'
NOTES = {
 1: ('父子死因按原始ICD-10边界保留，不能加总为互斥死亡人数。机器可读源表保留outcome_id。', 'Original ICD-10 boundaries are retained. Nested categories cannot be added as mutually exclusive deaths. The machine-readable source retains outcome_id.'),
 3: ('2009—2020年，每年49个有观测州级单位（含DC）；每单位等权。均值、中位数与P10/P90单位为μg/m³，分位范围不是CI。Alaska和Hawaii缺失而非零。', 'Each year from 2009–2020 includes 49 observed jurisdictions, including DC, with equal jurisdiction weights. Means, medians and P10/P90 are in μg/m³. Percentiles are distributional, not CIs. Alaska and Hawaii are missing, not zero.'),
 4: ('每县先对2009—2020年12年等权平均，再按县等权概括州内分布；浓度单位为μg/m³。全部256县保留。', 'Each county first averages the 12 years of 2009–2020 equally; counties then receive equal weight within each state. Concentrations are in μg/m³. All 256 counties are retained.'),
 5: ('每年256个唯一县—年。区域均值以当年县人口加权；中位数、P10/P90和Gini按县等权。浓度单位为μg/m³；Gini无量纲，分位数不是CI。', 'Each year contains 256 unique county-years. Regional means use current-year county population weights; medians, P10/P90 and Gini use equal county weights. Concentrations are in μg/m³; Gini is dimensionless and percentiles are not CIs.'),
 6: ('五分组由固定县级劣势划分，1为最低、5为最高。浓度为每县2009—2020年的长期均值，单位μg/m³；组内按县等权，不重新分组。', 'Quintiles use fixed county disadvantage, from 1 (lowest) to 5 (highest). Concentrations are county long-term means for 2009–2020 in μg/m³, equally weighted within each group. Groups are not redefined.'),
 7: ('81条当前观察期归档记录产生89次州归属；六州55次归属来自53条不同记录。跨州及潜在重复记录保留，不代表独立火灾数、死亡或烧毁面积贡献。完整目录见补充数据3。', 'The 81 in-period archived records yield 89 state assignments; 55 assignments in the six states arise from 53 distinct records. Cross-state and potentially duplicated records remain. Counts are not independent fires or contributions to mortality or burned area. Supplementary Data 3 supplies the full catalogue.'),
 8: ('各结局分母均为3,072条县—年；公开零值不属于Suppressed。隐藏死亡为州总量减公开县计数的余量，比例分母为对应州死亡总量，不是记录数。五类死因相互重叠，不可加总死亡。', 'Each outcome has 3,072 county-year records. Public zeros are not Suppressed. Hidden deaths are the state-total remainder after subtracting public county counts; their percentage uses state death totals, not record counts. Nested outcomes must not be added.'),
 9: ('四方法评价相同公开10—19计数单元，使用0—19支持和100份既有分配。所有指标越小越好，按评价单元等权；这是既存预测的当前子集汇总，不是重新训练。', 'All four methods evaluate the same publicly observed 10–19-count cells using support 0–19 and 100 saved allocations. Lower values are preferable for all three metrics; cells are equally weighted. These summarize the current subset of saved predictions, not retraining.'),
 10: ('区间为名义95%计数分配区间，不是死亡效应CI。宽度与评分按评价单元等权，区间评分越小越好；覆盖率需与95%及宽度一起解读。未新增bootstrap或CI。', 'Intervals are nominal 95% count-allocation intervals, not mortality-effect CIs. Width and interval score equally weight cells; lower interval score is preferable. Interpret coverage against 95% together with width. No bootstrap or new CI is produced.'),
 11: ('仅COPD，2009—2020年、3,072县—年。历史层级方案为3条链，每链预热200次、每10次保留一份，保留30份，共90份。区间为普通95% CI，接近的结果不是等效性检验，也不证明五结局联合一致。', 'COPD only, 2009–2020, with 3,072 county-years. The historical hierarchical scheme uses three chains, each with 200 warm-up iterations and 30 retained draws thinned every 10 iterations, totalling 90. Intervals are ordinary 95% CIs. Similar estimates do not establish equivalence or five-outcome joint consistency.'),
 12: ('逐份比较分母每关系为92,160（3,072县—年×30份）。任一份和均值列的单位均为不同县—年；全公开列为双方均公开的比较数/违反数。不同结局同编号不是联合后验样本，不能解释为违反概率或把关系间计数相加。', 'Each relationship has 92,160 draw-wise comparisons (3,072 county-years × 30 allocations). Any-draw and mean-count columns count distinct county-years; the public column gives jointly observed pairs / violations. Matching draw indices across outcomes are not joint posterior draws. Counts are neither posterior violation probabilities nor additive across relationships.'),
 13: ('FMI与Monte Carlo误差针对参考对数交互，MC/SE以百分数表示；α在同一模型30份拟合间固定，允许范围0.001—2。CIRC和IHD达到下界。种子为原始分配身份，不用于本轮重新抽样；抑制诊断另见补充表8。', 'FMI and Monte Carlo error refer to the reference log interaction; MC/SE is a percentage. Dispersion α is fixed across the 30 fits of a model and constrained to 0.001–2. CIRC and IHD reach the lower bound. Seeds identify original allocations, not a new sampling run. Suppression diagnostics are in Supplementary Table 8.'),
 14: ('所有模型含烟雾、烟雾×固定劣势、县和年份固定效应及年度人口offset。表内“加入”指在所列模型上增加字段。八模型均为同一3,062县—年。NW PM2.5指非野火代理；完整原始公式见Source Data。', 'Every model includes smoke, smoke × fixed disadvantage, county and year fixed effects, and annual population offset. Additions are relative to the named model. All eight models use the same 3,062 county-years. NW PM2.5 denotes the non-fire proxy; Source Data retain the full original formulas.'),
 15: (BASE_EFFECT_CN+' Holm P沿用原七项参考交互检验家族，没有按当前五项重算；未宣称前瞻性预注册，普通CI不是Holm同时区间。', BASE_EFFECT_EN+' Holm P values retain the original seven-reference-test family, without recalculation for five outcomes. Prospective preregistration is not claimed, and ordinary CIs are not Holm simultaneous intervals.'),
 16: ('单位为给定劣势下每固定IQR烟雾的100×(RR−1)。保留全部25个条件对比；普通双侧95% CI和P值均未作多重校正。15个区间全负、10个跨零、无全正区间。条件估计保留烟雾与交互协方差，不代表因果保护或额外死亡。', 'Values are 100×(RR−1) per fixed smoke IQR at the specified disadvantage. All 25 conditional contrasts are retained; ordinary two-sided 95% CIs and P values are not multiplicity-adjusted. Fifteen intervals are wholly negative, ten cross zero, and none is wholly positive. Contrasts retain smoke–interaction covariance and do not establish causal protection or additional deaths.'),
 17: (BASE_EFFECT_CN+' 八个C块模型均为同一3,062县—年；P未经多重校正。正文图4d使用此表M2与M3PL_joint，不使用A块3,072行替代。', BASE_EFFECT_EN+' All eight block-C models use the same 3,062 county-years; P values are unadjusted. Main Fig. 4d uses M2 and M3PL_joint from this table, not the 3,072-row block-A result.'),
 18: (BASE_EFFECT_CN+' “同时删除”指删除CA全部记录及全部州2020记录。“仅删除CA×2020”仅删CA的2020记录。P未经多重校正。不同显著性或重叠区间不能检验模型差异。', BASE_EFFECT_EN+' Omit CA and 2020 removes all CA records and all states’ 2020 records; omit CA in 2020 removes only CA’s 2020 records. P values are unadjusted. Differences in significance or overlapping CIs do not test between-model differences.'),
 19: (BASE_EFFECT_CN+' R为宽松QA、S为严格QA；−L/+L指不加/加入LST。同模型同QA分支内−L/+L样本相同；跨QA样本不同。严格分支均不含AZ。P未经多重校正，无跨模型差值推断。', BASE_EFFECT_EN+' R denotes relaxed QA and S strict QA; −L/+L omit/include LST. Each within-model, within-QA −L/+L pair has identical samples, whereas samples differ across QA branches. Strict branches exclude AZ. P values are unadjusted; no inference on between-model differences is supplied.'),
 20: ('分母为3,072个参考县—年。残差平方和先在完整参考设计中对其他设计变量投影，再分地域/年份汇总，未按人口加权。这是设计对比集中度，不是负二项信息量、死亡负担或因果贡献。', 'The denominator is 3,072 reference county-years. Residual sums of squares are computed once by projection on other variables in the full reference design, then partitioned by geography/year without population weights. This measures design-contrast concentration, not negative-binomial information, death burden or causal contribution.'),
 22: ('各行C/M2与C/M3PL_joint具有相同有序县年键、row_id与30份既有分配值；不能仅凭n相同证明配对。该参考列不是A块3,072县—年的参考模型。', 'Within each outcome, C/M2 and C/M3PL_joint share identical ordered county-year keys, row_id and all 30 saved count vectors. Equal n alone is not evidence of pairing. This reference column is not the 3,072-county-year block-A model.')
}

WIDTHS = {
 1:[22,113,35], 2:[23,74,73], 3:[22,27,30,30,30,31], 4:[15,21,23,23,22,22,22,22],
 5:[20,38,31,27,27,27],6:[36,24,27,27,28,28],7:[53,22,50,45],8:[20,29,25,30,33,33],
 9:[32,45,31,31,31],10:[32,45,31,31,31],11:[59,25,35,51],12:[28,23,21,22,50,26],
 13:[22,28,24,27,31,38],14:[34,112,24],15:[19,23,23,26,35,21,23],
 16:[20,29,26,29,41,25],17:[20,32,25,27,41,25],18:[19,39,24,26,38,24],19:[20,33,25,27,40,25],
 20:[66,26,35,43],21:[21,30,25,29,40,25],22:[20,23,32,28,20,25,22]
}


def variable_rows():
    cn = [['变量','定义及固定变换','来源及可追溯范围']]
    en = [['Variable','Definition and fixed transformation','Source and traceability']]
    pairs = [
      (['年度烟雾','每日浓度和÷365.25，μg/m³；固定IQR 0.678107947271523。','Childs产品的归档行政区聚合；字段已转换，精确本地提取标识不完整。'], ['Annual smoke','Sum of daily concentrations / 365.25, μg/m³; fixed IQR 0.678107947271523.','Archived administrative aggregation of the Childs product; conversion already applied. Exact local extraction identifier is incompletely archived.']),
      (['县级劣势','固定2006—2010基线复合分数；六州县间样本SD标准化，正向更不利。','NHGIS/ACS归档分数及下游标准化可追溯；完整组成、方向、权重和缺失规则不齐。'], ['County disadvantage','Fixed 2006–2010 baseline composite; standardized by sample SD across six-state counties; higher is more disadvantaged.','Archived NHGIS/ACS score and downstream scaling are traceable; complete components, directions, weights and missingness rules remain incomplete.']),
      (['死亡计数','公开县计数原样保留；Suppressed按州总量及1—9支持分配；公开零不变。','CDC WONDER归档30份县表及5份州表与当前面板逐键匹配；县级原始响应及完整日志未齐。'], ['Mortality counts','Public county counts retained; Suppressed counts allocated under state totals and support 1–9; public zeros fixed.','Thirty archived county export tables and five state tables from CDC WONDER match the current panel by key; original county responses and complete logs remain incomplete.']),
      (['年度人口','相应年度县人口；log(人口)作为offset，不以ACS基线人口替代。','CDC归档导出人口与面板匹配，采用对应年人口字段。'], ['Annual population','Corresponding annual county population; log(population) offset, not ACS baseline population.','Population in archived CDC exports matches the panel; the corresponding annual field is used.']),
      (['年龄结构','≥65岁人口比例，沿用归档固定标准化。','归档县年年龄字段可追溯；确切提取版本和上游处理链未完整归档。'], ['Age structure','Proportion aged ≥65 years, with the archived fixed standardization.','Archived county-year age field is traceable; exact extraction vintage and upstream processing are incompletely archived.']),
      (['人口密度','人口/面积后作log(1+密度)，再固定标准化。','归档Census土地面积关联；跨年份上游空间统一未由参考边界连接证明。'], ['Population density','Population / area, transformed as log(1+density), then fixed standardization.','Linked archived Census land area; reference-boundary matching does not establish upstream historical areal harmonization.']),
      (['干旱','火季D1或以上等级面积比例，沿用固定标准化。','归档县年干旱字段；具体产品批次和完整聚合链不齐。'], ['Drought','Fire-season area proportion at D1 or higher, retaining fixed standardization.','Archived county-year drought field; exact product batch and complete aggregation chain are incompletely archived.']),
      (['气温','5—10月均值，沿用归档固定标准化。','归档火季气温字段；精确产品版本、单位及提取链未完全认证。'], ['Temperature','May–October mean with the archived fixed standardization.','Archived fire-season temperature field; exact product version, units and extraction chain are not fully authenticated.']),
      (['降水','5—10月总量，沿用归档固定标准化。','归档火季降水字段；原始单位和精确提取版本不齐。'], ['Precipitation','May–October total with the archived fixed standardization.','Archived fire-season precipitation field; original units and exact extraction version remain incomplete.']),
      (['非野火PM2.5','总PM2.5减烟雾后固定标准化。','派生代理量，不是独立测量的来源组分；上游总PM2.5产品批次尚未完整认证。'], ['Non-fire PM2.5','Total PM2.5 minus smoke, followed by fixed standardization.','Derived proxy, not an independently measured source component; the exact upstream total-PM2.5 batch is not fully authenticated.']),
      (['臭氧','归档年度场，沿用固定标准化。','精确产品版本、原始单位及空间时间聚合链未完整归档。'], ['Ozone','Archived annual field, retaining fixed standardization.','Exact product version, original units and spatiotemporal aggregation chain are incompletely archived.']),
      (['白天地表温度','5—10月县面积/时间聚合；模型每10 °C。严格/宽松QA及覆盖阈值见方法7。','MOD11A2.061归档QC修正产品；只在有效LST配对像元恢复缺失QC=0，不等于个人热暴露。'], ['Daytime LST','May–October county area/time aggregation; per 10 °C in models. Strict/relaxed QA and coverage thresholds are in Methods 7.','Archived QC-corrected MOD11A2.061 product; missing QC=0 is restored only for paired valid LST pixels. This is not personal heat exposure.'])
    ]
    for a,b in pairs:
        cn.append(a); en.append(b)
    return cn,en


def prepare_tables():
    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / 'full_precision'
    full.mkdir(exist_ok=True)
    reverse = {v:k for k,v in CONFIG['table_map'].items()}
    config = json.loads((BASE / 'audit/inputs/health_config.json').read_text(encoding='utf-8'))
    result=[]; index=[]; checks=[]
    validation = records('validation.csv')
    with HISTORICAL.open(encoding='utf-8-sig', newline='') as hf:
        historical_reader = csv.DictReader(hf)
        historical_fields = list(historical_reader.fieldnames)
        historical_rows = list(historical_reader)
    subgroup = [r for r in validation if r['method']=='equal']
    scope_label = {'all_outcomes':'Pool', **dict(zip(IDS,LABELS))}
    sample_note = '; '.join(f"{scope_label[r['scope']]} {r['n_groups']} groups/{r['n_cells']} cells" for r in subgroup)
    for n in range(1,23):
        oldname = reverse.get(n)
        source = OLD / f'Table_{oldname}.csv' if oldname else OLD / 'model_formulas.csv'
        if n == 2:
            cn,en = variable_rows()
            notes=('这些定义区分当前可追溯字段与尚不完整的上游来源，不对缺失的单位、组成或权重作推定。州级贫困代理另见补充方法3，与县级综合劣势不同。', 'Definitions distinguish traceable analytical fields from incomplete upstream records; missing units, components or weights are not inferred. The separate state poverty proxy is described in Supplementary Methods 3 and is not the county composite index.')
        elif n == 13:
            old=load('Table_S3.csv')
            cn=[['结局','县—年数','FMI','MC/SE %','α','归档种子']]
            for oid, row in zip(IDS,old[1:]):
                cn.append([row[0],'3072',row[5],row[6],row[7],str(config['seed_map'][oid])])
            en=[['Outcome','County-years','FMI','MC/SE (%)','α','Archived seed']]+[row[:] for row in cn[1:]]
            notes=NOTES[n]
        elif n == 14:
            cn=[['模型','构造','县—年数'],['M0','烟雾 + 烟雾×劣势 + 县/年份固定效应','3062'],['M1','M0 + 年龄 + log(1+密度)','3062'],['M2','M1 + 干旱 + 气温','3062'],['M2P','M2 + 降水','3062'],['M3','M2 + 非野火PM2.5 + 臭氧','3062'],['M3L','M3 + LST','3062'],['M3P_joint','M3 + 降水','3062'],['M3PL_joint','M3 + 降水 + LST','3062']]
            en=[['Model','Construction','County-years'],['M0','Smoke + smoke × disadvantage + county/year fixed effects','3062'],['M1','M0 + age + log(1+density)','3062'],['M2','M1 + drought + temperature','3062'],['M2P','M2 + precipitation','3062'],['M3','M2 + non-fire PM2.5 + ozone','3062'],['M3L','M3 + LST','3062'],['M3P_joint','M3 + precipitation','3062'],['M3PL_joint','M3 + precipitation + LST','3062']]
            notes=NOTES[n]
        else:
            cn=load(f'Table_{oldname}.csv')
            if n == 1:
                cn=[row[1:] for row in cn]
            if n in [15,16,17,18,19]:
                cn[0][1]={15:'模型',16:'劣势水平',17:'模型',18:'删样本',19:'LST配对'}[n]
            en=[HEADERS[n]]+[[english(value) for value in row] for row in cn[1:]]
            notes=NOTES.get(n, ('',''))
        if n in [9,10]:
            notes=(notes[0]+' 样本量（组/单元）：'+sample_note.replace(' groups/','组/').replace(' cells','单元').replace('Pool','合并')+'。', notes[1]+' Sample sizes: '+sample_note+'.')
        if n == 21:
            notes=(
                '全部为历史COPD估计，区间为普通95% CI、P未经多重校正，各模型并非共同样本。O02：年龄+密度；O04：O02+干旱；O05：O04删2020；O06：O04改为时变劣势并保留其主项（2010—2020）；O03：PPML，年龄+密度，县/州×年固定效应；O07：O04，烟雾滞后1年；O08：O04，烟雾超前1年；O09：O04+总PM2.5+臭氧，仅ID/OR/WA，n=1,424；O11：M2+总PM2.5+臭氧，n=3,062；F06：M2早期2009—2016；F07：M2晚期2017—2020。总PM2.5不是新C块的非野火代理。没有新增模型差异检验。',
                'Historical COPD estimates only; intervals are ordinary 95% CIs and P values are unadjusted. Models do not share one common sample. O02: age+density. O04: O02+drought. O05: O04 omitting 2020. O06: O04 with time-varying disadvantage and its main effect (2010–2020). O03: PPML with age+density, county and state×year fixed effects. O07: O04 with 1-year-lagged smoke. O08: O04 with 1-year-leading smoke. O09: O04+total PM2.5+ozone in ID/OR/WA only (n=1,424). O11: M2+total PM2.5+ozone (n=3,062). F06: early M2, 2009–2016. F07: late M2, 2017–2020. Total PM2.5 is not the new block-C non-fire proxy. No new between-model test is performed.'
            )
        assert len(cn)==len(en) and all(len(a)==len(b) for a,b in zip(cn,en)), n
        assert not re.search(r'[\u3400-\u9fff]',json.dumps([en,TITLES[n][1],notes[1]],ensure_ascii=False)), n
        assert abs(sum(WIDTHS[n])-170)<1e-9, (n,WIDTHS[n])
        cnpath=OUT/f'Supplementary_Table_{n:02d}_CN.csv'
        enpath=OUT/f'Supplementary_Table_{n:02d}_EN.csv'
        # Table 1 CSV retains identifiers even though long IDs are omitted in Word.
        if n==1:
            original=load('Table_S1.csv')
            write(cnpath,original)
            write(enpath,[['outcome_id']+HEADERS[n]]+[[row[0]]+[english(v) for v in row[1:]] for row in original[1:]])
        else:
            write(cnpath,cn);write(enpath,en)
        full_sources=[]
        for name in SOURCES[n]:
            src=OLD/name;target=full/name
            if not target.exists():
                shutil.copy2(src,target)
            if digest(src)!=digest(target):
                raise RuntimeError('Full-precision destination differs: '+str(target))
            full_sources.append(str(target.relative_to(ROOT/'submission')))
            index.append(dict(table=n,role='full_precision',source_file=str(src),delivered_file=str(target.relative_to(ROOT/'submission')),sha256=digest(src),operation='byte-identical copy'))
        if n==13:
            seed_rows=[['outcome_id','abbreviation','seed','n_allocations']]+[[oid,lab,config['seed_map'][oid],30] for oid,lab in zip(IDS,LABELS)]
            seed_path=full/'allocation_seed_identity.csv';write(seed_path,seed_rows)
            full_sources.append(str(seed_path.relative_to(ROOT/'submission')))
            index.append(dict(table=n,role='allocation_identity',source_file=str(BASE/'audit/inputs/health_config.json'),delivered_file=str(seed_path.relative_to(ROOT/'submission')),sha256=digest(BASE/'audit/inputs/health_config.json'),operation='select retained five outcome seeds; no new allocations'))
        if n in [11,21]:
            if n==11:
                selected=[]
                for model in ['O10_temperature_adjusted_2009_2020', 'O10_hierarchical_EB_B1_method_sensitivity']:
                    match=[r for r in historical_rows if r['model_id']==model and r['cause_id']=='copd']
                    assert len(match)==1,(n,model,len(match))
                    selected+=match
                filename='historical_COPD_allocation_comparison.csv'
            else:
                selected=[]
                for row in cn[1:]:
                    prefix=row[0]+'_'
                    match=[r for r in historical_rows if r['model_id'].startswith(prefix) and r['cause_id']=='copd' and float(r['year_min'])>=2009 and float(r['year_max'])<=2020]
                    assert len(match)==1,(n,prefix,len(match))
                    selected+=match
                filename='historical_COPD_additional_models.csv'
            for saved in selected:
                if saved['year_min'] and saved['year_max']:
                    assert float(saved['year_min'])>=2009 and float(saved['year_max'])<=2020
                else:
                    # This historically reused row leaves year fields blank but
                    # explicitly identifies the same fixed-reference sample hash.
                    # Preserve blanks, never manufacture missing result fields.
                    assert n==11 and saved['model_id']=='O10_hierarchical_EB_B1_method_sensitivity'
                    assert saved['sample_hash']==selected[0]['sample_hash']=='e944bdd3083e646d'
                    assert saved['n_county_years']==selected[0]['n_county_years']=='3072'
            for shown,saved in zip(cn[1:],selected):
                estimate_ix=2 if n==11 else 3
                ci_ix=3 if n==11 else 4
                assert shown[estimate_ix].replace('−','-')==f"{float(saved['interaction_percent']):.3f}"
                expected_ci=f"{float(saved['CI_percent_lower']):.3f} 至 {float(saved['CI_percent_upper']):.3f}"
                assert shown[ci_ix].replace('−','-')==expected_ci
                if n==21:
                    assert shown[5].replace('−','-')==format(float(saved['P_value']),'.3g')
            target=full/filename
            write(target,[historical_fields]+[[r[k] for k in historical_fields] for r in selected])
            full_sources.append(str(target.relative_to(ROOT/'submission')))
            index.append(dict(table=n,role='full_precision_historical_selection',source_file=str(HISTORICAL),delivered_file=str(target.relative_to(ROOT/'submission')),sha256=digest(HISTORICAL),operation='select archived COPD model rows, retain every field verbatim including unavailable values; no inference recalculated'))
        item=dict(id=n,cn_title=TITLES[n][0],en_title=TITLES[n][1],cn_note=notes[0],en_note=notes[1],cn_rows=cn,en_rows=en,source_path=str(source),full_precision_source=full_sources,widths_mm=WIDTHS[n])
        result.append(item)
        checks.append(dict(table=n,rows=len(cn)-1,columns=len(cn[0]),bilingual_shape_equal=True,english_contains_chinese=False,source_sha256=digest(source),cn_display_sha256=digest(cnpath),en_display_sha256=digest(enpath),status='PASS'))
    assert [t['id'] for t in result]==list(range(1,23))
    assert sum(len(t['cn_rows'])-1 for t in result if t['id'] in [15,16,17,18,19])==135
    write(OUT/'full_precision_source_index.csv',[list(index[0])]+[[r[k] for k in index[0]] for r in index])
    audit=ROOT/'audit'
    write(audit/'table_asset_checks.csv',[list(checks[0])]+[[r[k] for k in checks[0]] for r in checks])
    (audit/'table_assets.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    tables=prepare_tables()
    print(json.dumps({'tables':len(tables),'table_rows':{t['id']:len(t['cn_rows'])-1 for t in tables},'health_rows':sum(len(t['cn_rows'])-1 for t in tables if 15<=t['id']<=19)},ensure_ascii=False))
