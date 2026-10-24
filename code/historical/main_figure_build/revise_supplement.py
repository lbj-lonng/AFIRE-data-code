"""Scope-filter the latest full SI, retaining all in-scope evidence and native formulas."""
from environment import ROOT,SUB,SD,AUD
from scope import IDS,LABELS
import json,re
import pandas as pd

def read(name):return pd.read_csv(SD/f'full_results/{name}.csv',float_precision='round_trip')
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(x) for x in row)+' |' for row in rows])
def prepare_markdown():
    text=(AUD/'inputs/Supplementary_Information_CN.md').read_text(encoding='utf-8')
    changes=[]
    def paragraph(prefix,new):
        nonlocal text
        lines=text.splitlines();ix=[i for i,l in enumerate(lines) if l.startswith(prefix)];assert len(ix)==1,(prefix,ix)
        changes.append({'prefix':prefix,'old':lines[ix[0]],'new':new});lines[ix[0]]=new;text='\n'.join(lines)+'\n'
    paragraph('本补充材料与正文','本补充材料与正文两个研究问题及图1—4配套，观察期均为2009—2020年，提供州至县暴露定义、死亡资料处理、五类结局完整估计和不确定性、环境调整、删样本分析及来源核验。表S5—S9呈现135行健康结果。保留既有Holm校正值及其原7项检验家族，不因当前报告范围重算。火灾目录的上游排名与事件去重来源仍未闭合，其限制与当前时段记录明细一并保留。')
    paragraph('健康分析采用','健康分析采用已冻结结果中五类结局的估计。原有约束分配数组与计算引擎用于确认估计身份，关联面板和协变量提供统计定义。对当前结果、样本键和插补数组核对来源哈希；本次没有重新生成分配、拟合死亡模型或新增推断性检验。')
    paragraph('完整输入为','本稿纳入15,360行县—年—死因记录，即256县、12年（2009—2020）及五类结局。每项参考分析使用3,072个县—年。暴露描述以唯一县—年为单位，不使用重复五次的死因行加权。offset使用对应年度人口。县FIPS、年份与死因共同识别记录，row_id恢复插补数组列对应关系。这些是五类汇总死亡结局，不是病例数或独立患者队列。')
    paragraph('死因类别相互重叠','死因类别相互重叠，不能相加为独立死亡。各类别沿用原始ICD-10边界，不从广义类别中扣除任何组成诊断。各州县数为AZ 15、CA 58、CO 64、ID 44、OR 36、WA 39。固定劣势指数范围为−2.852336至3.417321 SD；五个条件关联评估水平位于该范围内，但范围内并不等于局部暴露重叠充分。')
    paragraph('被抑制单元和公开零值','被抑制单元和公开零值的分母均为每结局3,072个县—年。隐藏死亡百分比由公开州总量减去公开县计数得到的余量之和，除以对应州死亡总量之和；与受抑制记录比例的分母不同。所有360个州—年—死因组的总量约束在既有30份数组中均成立。FMI和Monte Carlo误差针对对数交互；$\\alpha$在同一模型各份拟合中固定。循环系统和缺血性心脏病达到其下限。全部模型诊断见model_diagnostics.csv。')
    paragraph('补充表 S5–S9 依次包含','补充表S5—S9依次包含A = 5、B = 25、C = 40、D = 25、E = 40行，共135行。五类结局对应110个既有模型任务，每个保存30份成功拟合；B的五个条件对比共享其A任务，不是新增回归。联合键为outcome_id + analysis_block + model_id + contrast_id。估计与区间显示三位小数，P值显示三位有效数字且不舍入为零。Source Data保留未舍入数值、年份、样本哈希、公式、离散度与诊断。C全部n = 3,062；D、E单独列出各行n。')
    paragraph('较早的伪抑制比较','既有伪抑制比较选择公开10—19计数，暂时隐藏单元值而保留总和约束，分配支持为0—19，并在历史率学习中排除完整目标年。本稿从保存的逐单元预测中筛选2009—2020年及五类结局，四方法使用相同298组、2,128单元，每方法100份已存分配；未重新训练或分配。评价期筛选不改变既有训练窗口：原训练资料覆盖2006—2020年，每个目标年均从训练中完整排除。因此这是既有方法在当前评价子集上的表现，不是仅用当前研究期重新训练的验证。其经验计数区间覆盖率不是实际1—9受抑制计数或目标烟雾交互的覆盖率；验证Gamma–Poisson EB权重学习与主要固定权重构造不同。历史COPD重建敏感性也不等于五类结局的联合一致性证明。')
    paragraph('健康结果沿用冻结','健康结果沿用冻结的135行估计。补充表S5—S9与源表逐行对应；本次重核五类结局共同样本模型的县—年键、实际分配数组和30份拟合记录，见表S23。跨死因包含关系由既有数组重新计数，不生成新分配；验证指标由筛选后的逐单元记录汇总，不重新训练或进行bootstrap。历史核验与本轮检查分别记录，未将历史检查冒称本轮重新执行。算术一致不等于统计校准，也不自动闭合上游来源。')
    paragraph('每年均为256县','2009—2020年每年均为256县，共3,072个唯一县—年。年度暴露按归档每日浓度和÷365.25定义；人口加权均值使用对应年度人口，不将每个结局重复计入。Gini对县赋相同权重。五分位以固定基线劣势分组，暴露为每县12年平均，各组县数为52/51/51/51/51。已存描述性Spearman $\\rho=0.0825603685$保持不变；不把重复县—年当作独立样本新增相关检验。')
    paragraph('历史全国序列的人口权重','历史全国序列的人口权重和地域覆盖来源未闭合，因此不用于全国均值、全国增长或不平等持续恶化主张。S14州等权汇总不是人口加权全国估计。完整72行研究期州—年及256县均值分别见county_aggregated_state_year.csv和county_map_values.csv。')
    paragraph('稳定的FIPS和县名','稳定FIPS和县名支持参考边界展示，却不能完整认证上游历史面积聚合口径。输入虽含2020年土地面积字段，不能据此证明每个历史输入使用相同多边形。本稿未编造缺乏依据的crosswalk，地理审计保留这一限制。劣势图使用真实2006—2010年基线指数，与随访前两年重叠；不是经济因果效应或县级死亡效应地图。烟雾字段已在上游由每日和转换为年度浓度，本次不重复除以365.25。县均值、州/区域序列及死亡压制汇总均限于2009—2020年。')
    paragraph('新增源数据保留','当前源数据保留15,360条原始抑制标记及3,072条唯一县—年暴露描述记录。每县60条死亡记录，覆盖12年中每年的五类结局。图3a是记录被抑制比例，不是不重复死亡比例。图2d保留全部县及固定五分位，区分均值与箱线中位数。补充图S6呈现72个州—年人口加权值。')
    paragraph('表S12分母为','表S12与表S3均使用2009—2020年每死因3,072条记录；隐藏比例分母为相应州—年—死因总量之和。零是公开零而非抑制。五类死因相互重叠，不可加总死亡。主要固定权重相当于使用州内县—年人口中位数的3倍作先验等效暴露，再结合可见历史计数；权重固定后保存30份分配。既有历史权重构造及其不确定性未因本次报告范围变化而重新估计。')
    cv=read('validation');v=cv[cv.scope.eq('copd')].iloc[0]
    paragraph('历史验证在每个目标年',f'本稿验证评价子集为298组、2,128单元，其中COPD为{int(v.n_groups)}组、{int(v.n_cells)}单元。各方法的逐单元键、真值及评价年份完全一致；使用既有预测与评分列重算当前子集的点指标。Gamma–Poisson验证家族的先验等效暴露学习及回退规则保持原样。没有重用完整旧评价范围的汇总值或bootstrap区间，也没有生成新的bootstrap或显著性检验。真实历史训练窗口与留年方式见S8。')
    paragraph('新增州级背景仅使用','州级背景只使用2009—2020年现有暴露字段，不使用死亡数、年龄标化死亡率或健康负担成分。五类重复记录的暴露值一致后，按唯一州—年汇总。51×12名义面板中Alaska和Hawaii全期缺暴露，实际为49×12 = 588个观测；DC保留。对行政单位等权计算年度均值、中位数和第10—90百分位。此检查验证下游汇总，不证明上游县至州聚合权重。')
    paragraph('归档全国人口加权均值','归档全国人口加权均值和Gini不作为本稿发现。既有SES人口与暴露表人口字段不能同时复现原汇总，无法仅凭列名认证全国年度人口权重。这一来源限制保留，但旧数值、增长倍数及趋势检验只存于内部审计，不用于当前结论。没有重新拟合推断性趋势。')
    paragraph('本次定位到原有100行','本稿火灾背景按事件年份从既有目录筛得81条记录、89次州归属，涉及13州。六州55次归属来自53条不同目录记录，不能解释为独立事件数或火灾贡献比例。跨州及潜在重复均保留；不会因Alaska无烟雾观测而删除其目录记录。表S21—S22保留当前子集的完整分母及记录。州级经济指标使用固定基线贫困比例，与县级综合劣势变量不同。')
    bridge=read('state_county_bridge');ad=bridge.difference_saved_minus_current.abs()
    paragraph('90行跨尺度比较',f'72行跨尺度比较保留六州2009—2020年现有州级暴露及用县级浓度、对应年度人口重建的州均值。平均绝对差异为{ad.mean():.6f} μg m−3，最大绝对差异为{ad.max():.6f} μg m−3；现有州值除以县聚合州值的比值为{bridge.ratio_saved_over_current.min():.6f}至{bridge.ratio_saved_over_current.max():.6f}。接近的一致性提供描述性衔接，但不证明权重相同或历史边界统一。正文州、县地图均平均2009—2020年，保留各自色标与来源定义。')
    paragraph('州内县分布使用','州内县分布使用全部256县2009—2020年等权年度均值。补充图S7展示每县，包括须外观察值，不增加置信区间，也不将县当作独立推断重复。表S17—S19提供年度、州内与跨尺度值；588个有观测州—年、51单位缺失台账、72个匹配对比及256县点均在Source Data中提供。')
    paragraph('差值为现有州值','差值为现有州值减去县级人口加权聚合州值，浓度单位为μg/m³；比值为前者除以后者。每州保留12年，不能将微小差异解释为权重或历史边界完全一致。')
    paragraph('正文图1d使用现存','正文图1d仅使用既有Top100归档目录中事件年份为2009—2020年的81条记录，不重新筛选全库或重新排名。保留原Rank和标识；SizeMetricAcres与GIS_ACRES一致，仅证明本地排序字段，不认证该时期全国最大事件集合或独立事件去重。按intersect_states拆分州归属，缺少相交州时使用已有质心州，跨州记录在每州计一次。81条共89次归属，其中8条跨州；具体定位方式保留在Source Data。')
    paragraph('资料状态仍为PARTIAL','目录来源仍为PARTIAL：缺少原始边界/点位获取日期、查询与版本、Rank生成及事件去重脚本。当前子集同名同年检查标记12组、28条潜在重复，未证明为同一火灾，也未删除或合并。六州55次归属来自53条不同目录记录，不等于独立火灾，也不是死亡、烟雾或烧毁面积贡献比例。现有范围不能事后改写为预先筛选过程或全国代表性。')
    paragraph('面积列为归档GIS_ACRES','面积列为归档GIS_ACRES，单位英亩；面积仅说明既有排序字段，并非本文新计算的烧毁面积。疑似重复为同一规范化名称和年份出现多次。当前子集保留全部原始标识、缺失名称、逐条州归属和原始Rank；没有重新填补、去重或排名。')
    # Only historical training/baseline/source years survive in prose, never observation-year rows.
    swaps={'完整七结局':'五类结局完整','七结局完整结果':'五类结局完整结果','七结局等效':'五类结局等效','新的七结局验证':'新的五类结局验证','七项 A 参考交互':'原7项A参考交互（保留已存校正，不重算）','原七结局共同样本结果':'五类结局共同样本结果','diagnostics_7outcomes.csv':'model_diagnostics.csv','Supplementary_Data_1.csv':'health_results.csv','Supplementary Data 1':'health_results.csv','model_formula_dictionary.csv':'model_formulas.csv','全部 35 个对比':'全部25个对比','固定七结局顺序':'固定五类结局顺序','全部 56 行（七结局×八模型）':'全部40行（五类结局×八模型）','全部 35 个交互':'全部25个交互','E 区块全部 56 行':'E区块全部40行','90个州—年汇总（六个研究州×2006—2020年）':'72个州—年汇总（六个研究州×2009—2020年）','暴露的90个匹配值':'暴露的72个匹配值','完整100行目录及疑似重复标记':'2009—2020年目录子集及疑似重复标记','原七项主要检验家族':'原主要检验家族','七项主要检验家族':'原主要检验家族','state_year.csv':'county_aggregated_state_year.csv','FigureS7_county_points.csv':'Supplementary_Figure_S7_data.csv','本地100行目录':'原归档目录','../04_figures/supplementary/':'figures/supplementary/'}
    for a,b in swaps.items():text=text.replace(a,b)
    text=text.replace('county_aggregated_county_aggregated_state_year.csv','county_aggregated_state_year.csv')
    # Filter old table rows by explicit labels, keeping the parent disease definitions intact.
    banned=re.compile(r'asthma|cerebrovascular|\bASTH\b|\bCEREB\b|哮喘|脑血管',re.I)
    lines=[];section=''
    for line in text.splitlines():
        if line.startswith('### 补充表 '):section=line
        if line.startswith('|') and banned.search(line):continue
        if line.startswith('|'):
            cells=[s.strip() for s in line.strip('|').split('|')]
            if re.search(r'补充表 S(10|17)\b',section) and cells[0] in ['2006','2007','2008']:continue
            if '补充表 S19 ' in section and len(cells)>1 and cells[1] in ['2006','2007','2008']:continue
            if '补充表 S22 ' in section and len(cells)>2 and cells[2] in ['2006','2007','2008']:continue
            if '补充表 S16 ' in section and '2006' in line:continue
        lines.append(line)
    text='\n'.join(lines)+'\n'
    def replace_table(sid,new):
        nonlocal text
        pat=r'(### 补充表 '+re.escape(sid)+r'\b[^\n]*\n(?:(?!\n###|\n##)[\s\S])*?)(\|[^\n]+\n(?:\|[^\n]*\n)*)'
        text,n=re.subn(pat,lambda m:m[1]+new+'\n',text,count=1);assert n==1,sid
    nested=read('nested_outcome_check')
    replace_table('S4',table(['关系','逐份','任一份','均值','全公开 n/违反','最大超出'],[[r.relation.replace(' subset ',' > '),f'{r.draw_violations:,}',r.any_draw_violations,r.mean_count_violations,f'{r.public_comparisons:,} / {r.public_violations}',r.max_excess] for r in nested.itertuples()]))
    sup=read('suppression').set_index('cause_id').loc[IDS]
    replace_table('S12',table(['死因','抑制记录数','公开零记录数','隐藏死亡数','抑制记录 %','隐藏死亡 %'],[[lab,int(r.suppressed),int(r.public_zero),int(r.hidden_deaths),f'{r.record_percent:.3f}',f'{r.hidden_percent:.3f}'] for lab,(_,r) in zip(LABELS,sup.iterrows())]))
    methods={'equal':'等权','population':'人口权重','loyo_fixed_EB':'固定EB','loyo_hierarchical_EB':'层级EB'}
    scopes={'all_outcomes':'五类合并',**dict(zip(IDS,LABELS))}
    replace_table('S13a',table(['范围','方法','MAE','RMSE','CRPS'],[[scopes[r.scope],methods[r.method],f'{r.MAE:.3f}',f'{r.RMSE:.3f}',f'{r.mean_CRPS:.3f}'] for r in cv.itertuples()]))
    replace_table('S13b',table(['范围','方法','覆盖率 %','区间宽度','区间评分'],[[scopes[r.scope],methods[r.method],f'{100*r.coverage_95:.3f}',f'{r.mean_interval_width:.3f}',f'{r.mean_interval_score_95:.3f}'] for r in cv.itertuples()]))
    fires=read('fire_state_counts').sort_values(['catalogue_record_assignments','state_abbr'],ascending=[False,True])
    replace_table('S21',table(['州','州缩写','目录归属次数','六州范围'],[[r.state,r.state_abbr,int(r.catalogue_record_assignments),'是' if r.in_six_state_region else '否'] for r in fires.itertuples()]))
    # Existing S22's selected rows retain the same rank, area and duplicate flag.
    assert not banned.search(text),banned.findall(text)
    assert not any(x in text for x in ['26,880','3,840','189行','495组','3,302','735个','105条','七结局','七类结局']), 'stale scope'
    (AUD/'supplement_change_details.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
    return text

def run():
    import supplement_formatter as fmt
    fmt.prepare_markdown=prepare_markdown
    fmt.build()
    main=(AUD/'inputs/previous_equations.tex').read_text(encoding='utf-8')
    # Mathematics is invariant to the reporting subset; keep the canonical source.
    (SUB/'equations.tex').write_text(main,encoding='utf-8')
if __name__=='__main__':run()
