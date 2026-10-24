"""Explicit final evidence/terminology/numbering ledgers; no estimates or data edits."""
from environment import ROOT, SUB, AUD, BASE, SD
import csv, json, hashlib
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,rows):
    assert rows
    with (AUD/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    cfg=json.loads((ROOT/'scripts/scope_config.yaml').read_text(encoding='utf-8'))
    oldsi=BASE/'submission/Supplementary_Information_CN.md'
    assert oldsi.is_file()
    maps=[]
    for kind,key,newname in [('table','table_map','Supplementary Table'),('figure','figure_map','Supplementary Fig.'),('data','data_map','Supplementary Data')]:
        for old,new in cfg[key].items():
            maps.append(dict(kind=kind,old_version=str(BASE),old_location=('Table ' if kind=='data' else kind.title()+' ')+old,new_location=f'{newname} {new}',decision='迁入数据附件' if kind=='data' else '连续重编号',source=str(oldsi),source_sha256=sha(oldsi),scope='Current five-outcome baseline; earlier versions resolved in version_content_migration.csv'))
    maps.append(dict(kind='table',old_version=str(BASE),old_location='NEW: consolidated frozen model definitions',new_location='Supplementary Table 14',decision='汇总八个冻结模型定义，不是新增模型',source=str(SD/'full_results/model_formulas.csv'),source_sha256=sha(SD/'full_results/model_formulas.csv'),scope='Actual eight-branch definitions'))
    for old,new in cfg['section_map'].items():
        maps.append(dict(kind='section',old_version=str(BASE),old_location=old,new_location=new,decision='主题合并/精确指向',source=str(oldsi),source_sha256=sha(oldsi),scope='Section map; not interchangeable with numbered table/figure map'))
    for n in range(1,13):
        maps.append(dict(kind='equation',old_version='multiple historical definitions',old_location='Historical expressions are merged/corrected by topic, not one-to-one numbering',new_location=f'Supplementary Equation ({n})',decision='按冻结实现连续编号；不伪造旧公式一对一身份',source=str(ROOT/'scripts/equations.py'),source_sha256=sha(ROOT/'scripts/equations.py'),scope='Exact expression source and corrections documented in Methods and migration ledger'))
    write('old_to_new_numbering.csv',maps)
    # Each entry links a concrete current claim to actual saved evidence and its boundary.
    specs=[
        ('观察范围与五类ICD定义','outcome_dictionary.csv','Methods 1; Table 1','Results 1–2','固定白名单；父类/子类不能相加为不同死亡','按既有outcome_id顺序保留，不重构死因'),
        ('六州256县、3072参考县年及15360死亡记录','mortality_records.csv','Methods 1; Tables 5, 8','Results 1–2','同县年不得按五类死因重复加权暴露','唯一FIPS/year、原公开数/抑制标志；不填补'),
        ('公开零、Suppressed、缺失与州总量约束','state_death_remainders.csv','Methods 4; Tables 8, 12','Results 2 / Figure 3','支持集1–9，公开零固定；不是恢复真值','读取既有州年死因余量及可行性'),
        ('49有观测州级单位含DC，AK/HI缺失','state_year_exposure_with_missing.csv','Methods 2; Note 1; Tables 3–4','Results 1 / Figure 1','缺失不等于零，背景灰色不等于无暴露','保留全部州级缺失台账；观察子集2009–2020'),
        ('州等权年度描述与县人口加权汇总不同','state_annual.csv','Methods 2; Note 1; Tables 3–5','Results 1 / Figures 1–2','P10–P90为分布范围不是CI','不混用州权重与县人口权重'),
        ('72对州县暴露桥接','state_county_bridge.csv','Note 1; Supplementary Data 2; Fig. 1','Results 1 / Figures 1–2','近似一致不证明上游权重或历史边界完全一致','按州/年原值逐对比；不重新估计'),
        ('州内县分布及固定劣势分组','within_state_county_distribution.csv','Note 1; Fig. 2; Table 6','Results 1 / Figure 2','弱或非单调梯度不是无经济因果影响的证明','县等权描述；固定既有劣势分组'),
        ('县FIPS与2020行政边界连接','county_geographic_join.csv','Methods 2; Source Data geography README','Results 1 / Figure 2','完整连接不等于历史边界已经逐年统一','精确5位FIPS；旧105行分母表仅内部追溯'),
        ('州级贫困代理的县总人口加权定义','state_baseline_poverty.csv','Methods 3; Note 2; Supplementary Data 1','Results 1 / Figure 1','非直接官方州贫困率，非县级综合劣势指数','49个有烟雾观测州单位；真实2006–2010基线'),
        ('81条火灾记录与89次州归属','fire_record_state_assignments.csv','Methods 3; Note 2; Table 7; Supplementary Data 3','Results 1 / Figure 1','六州55归属/53目录记录；不是独立事件Top100或贡献率','跨州分别计归属；保留潜在重复不重排'),
        ('固定EB与层级伪抑制四法完整验证','validation_evaluation_records.csv','Methods 5; Note 3; Tables 9–10','Results 2 / Figure 3','同298组2128单元；分配覆盖率不校准死亡效应','仅汇总已存单元评价量；0–19/100份与主1–9/30份不同'),
        ('参考交互及原七项Holm保存值','primary.csv','Methods 6; Note 5; Table 15','Results 2 / Figure 4','当前五项范围未预注册；普通CI不是Holm同时区间','保存P_adjusted不重算；A块5行'),
        ('全部25个条件关联及负向/跨零区间','conditional.csv','Methods 6; Note 5; Table 16; Fig. 4','Results 2 / Figure 4','正交互不等于各劣势水平正关联或额外死亡','B块25行，保留协方差形成的冻结CI/P'),
        ('八模型共同样本的40个交互结果','common_sample.csv','Methods 7; Note 5; Tables 14, 17; Fig. 5','Results 2 / Figure 4','无跨模型协方差，不新算差值CI/P或等效性','C块40行3062共同样本；M3不含降水'),
        ('共同样本行序和30份分配身份','common_sample_identity.csv','Methods 7; Table 22','Results 2 / Figure 4d','相同n不充分；本次额外只读数组核验见数值审计','FIPS/year/row_id/行序/对应分配向量联合认证'),
        ('定向删除后的25项结果','targeted_omissions.csv','Note 5; Table 18; Fig. 6','Results 2 / Figure 4','保留IHD负向点估计及跨零区间，不能以显著性有无证明差异','D块全部25行，不重新删除拟合'),
        ('strict/relaxed LST配对40项结果','LST_pairs.csv','Methods 7; Note 5; Table 19; Fig. 7','Results 2 / Figure 4','strict与relaxed不同地理/样本范围；LST非个人热暴露','E块40行；同一分支内−L/+L配对而非全样本比较'),
        ('三项父子关系数组不一致','nested_outcome_check.csv','Note 4; Table 12; Fig. 3','Results 2 / Figure 3','同编号不是联合后验；不能相加违反数或推联合负担','原始保存数组诊断；公开计数对照无违反'),
        ('CA×2020设计对比集中','design.csv','Note 6; Table 20','Results 2 / Figure 4','残差平方和不是死亡负担、因果贡献或效应来源证明','既有设计残差汇总；1.888%行对应39.417%平方和'),
        ('固定权重/离散度、FMI、MCSE与种子','model_diagnostics.csv','Methods 4, 6; Table 13','Results 2 / Figures 3–4','低FMI不包含全部上游/固定条件不确定性','按冻结引擎传统Rubin与实际FMI，不重估离散度'),
    ]
    claims=[]
    for idx,(claim,filename,dest,mainloc,boundary,transform) in enumerate(specs,1):
        path=SD/'full_results'/filename;assert path.is_file(),path
        claims.append(dict(claim_id=f'C{idx:02d}',claim_CN=claim,evidence_file=str(path),evidence_sha256=sha(path),filter_or_transform=transform,SI_destination=dest,main_destination=mainloc,interpretation_boundary=boundary,status='TRACEABLE_FROZEN_EVIDENCE'))
    extras=[
        ('主要固定EB权重身份与真实历史构造',AUD/'upstream_eb_weight_identity.json','Methods 4; Equations (4)–(6)','主固定权重不排除目标年；先验乘数3的原选择理由仍缺'),
        ('传统Rubin/离散度/FMI/条件关联的完整可编辑定义',ROOT/'scripts/equations.py','Methods 4, 6; Equations (1)–(12)','公式复述原实现；不声称本轮估计或Barnard–Rubin'),
        ('历史COPD单结局辅助比较与额外模型',SD/'tables/full_precision_source_index.csv','Methods 5; Tables 11, 21','仅纳入身份/时间可证的原结果，不外推为五结局联合验证'),
        ('最新作者稿只同步引用且保留解释风险',AUD/'maintext_sync_integrity.json','author_action_needed.md; maintext_changes.md','摘要限定被作者外部删除；本次不擅自恢复，全文解释仍PARTIAL'),
    ]
    for claim,path,dest,boundary in extras:
        assert path.is_file(),path
        claims.append(dict(claim_id=f'C{len(claims)+1:02d}',claim_CN=claim,evidence_file=str(path),evidence_sha256=sha(path),filter_or_transform='只读身份核验；科学判断另见对应主题审计',SI_destination=dest,main_destination='Results 2 / Figures 3–4' if '作者' not in claim else 'Actual current author manuscript',interpretation_boundary=boundary,status='TRACEABLE_WITH_STATED_LIMIT'))
    write('claim_evidence_map.csv',claims)
    terms=[
        ('研究观察期','study observation period','2009–2020','区分基线、训练、产品及文献年份','Methods 1'),
        ('县—年','county-year','FIPS × year','非30份分配×观测的独立样本','Methods 1'),
        ('州—年—死因组','state–year–cause group','约束守恒的组','非回归聚类单位','Methods 4'),
        ('县级社会经济劣势','county-level socioeconomic disadvantage','固定2006–2010复合分数，六州间标准化','不与州贫困代理互换，未知构成不臆造','Methods 3'),
        ('州级贫困代理','state-level poverty proxy','县贫困比例按县总人口加权','非直接官方州级贫困率','Methods 3'),
        ('年均烟雾浓度','annual mean smoke concentration','原每日和/365.25，μg/m³','已转换字段不可再除一次','Methods 2; Equation (1)'),
        ('固定烟雾IQR','fixed smoke IQR','0.678107947271523 μg/m³','不按结局或删样本重新缩放','Methods 1, 6'),
        ('受抑制死亡计数','suppressed death count','主分配支持1–9','区别公开零与缺失，不称真实隐藏值恢复','Methods 4'),
        ('约束分配','constrained allocation','既有30份条件分配','不是30个独立研究或联合后验','Methods 4'),
        ('固定经验贝叶斯','fixed empirical Bayes','主要固定历史率强度','不排除目标年，不与留年验证混写','Methods 4'),
        ('伪抑制验证','pseudo-suppression validation','公开10–19；支持0–19；已存100份','评价子集改变不等于重新训练','Methods 5'),
        ('留出整个目标年','leave-one-year-out','验证历史训练排除整年','不用于描述主固定EB权重','Methods 5'),
        ('比值之比','ratio of rate ratios (RRR)','烟雾×劣势交互','不是每个劣势水平的条件RR','Methods 6'),
        ('条件关联','conditional association','给定劣势水平的烟雾RR','必须保留主效应/交互/协方差','Methods 6; Equation (12)'),
        ('普通95%置信区间','ordinary 95% confidence interval','双侧、非同时区间','不是Holm同时CI','Methods 6'),
        ('原七项Holm家族','original seven-test Holm family','A块保存的校正P值','不按五项重算，不宣称预注册','Methods 6; Table 15'),
        ('共同样本','common sample','C块3062行且键/行序/数组身份相同','不能只凭相同n判断配对','Methods 7; Table 22'),
        ('定向删除','targeted omission','既有删除年份/地区的模型','不声称差值检验、因果影响来源或等效','Note 5'),
        ('地表温度','land surface temperature (LST)','May–October daytime MOD11A2.061','不是个人热暴露；严格/宽松样本不同','Methods 7'),
        ('包含关系诊断','nested-outcome diagnostic','保存数组的父子计数比较','不是联合后验违反概率，结局不可相加','Note 4'),
        ('设计残差平方和','design residual sum of squares','对比集中性描述','不是死亡负担、归因分数或因果贡献','Note 6'),
        ('火灾目录记录','fire catalogue record','既有归档目录的记录','区别州归属次数及独立事件数量','Methods 3; Note 2'),
        ('州/县分布P10–P90','P10–P90 distribution range','描述性分位范围','不是置信区间','Methods 2'),
        ('传统Rubin合并','conventional Rubin pooling','冻结引擎定义/自由度','不是Barnard–Rubin；FMI按实际公式','Methods 6'),
    ]
    write('terminology_ledger.csv',[dict(CN=a,EN=b,operational_definition=c,forbidden_conflation_or_boundary=d,location=e) for a,b,c,d,e in terms])
    print(json.dumps({'numbering_rows':len(maps),'claim_rows':len(claims),'term_rows':len(terms),'source_paths_and_hashes_verified':True},ensure_ascii=False))

if __name__=='__main__':main()
