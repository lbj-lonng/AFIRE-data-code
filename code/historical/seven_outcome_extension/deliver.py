"""Independent pooling validation, complete tables, figures and Chinese reports."""
import run_extension as r
import json, math, sys, subprocess, shutil
import numpy as np
import pandas as pd
from scipy.stats import t, norm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from statsmodels.stats.multitest import multipletests
O=r.OUT
def independent_pool(q,u):
    q=np.asarray(q,float);u=np.asarray(u,float)
    assert len(q)==30 and np.isfinite(q).all() and np.isfinite(u).all() and (u>=0).all()
    b=q.mean();w=u.mean();v=q.var(ddof=1);total=w+31/30*v;se=np.sqrt(total);rel=31/30*v/w if w else np.inf
    df=29*(1+1/rel)**2 if np.isfinite(rel) and rel>0 else 1e12
    crit=t.ppf(.975,df) if df<1e8 else norm.ppf(.975)
    p=2*t.sf(abs(b/se),df) if df<1e8 else 2*norm.sf(abs(b/se))
    return dict(beta=b,SE=se,beta_CI_lower=b-crit*se,beta_CI_upper=b+crit*se,P_value=p,within_variance=w,between_imputation_variance=v,total_variance=total,df_rubin=df,n_imputations=30,monte_carlo_error=np.sqrt(v/30),fraction_missing_information=(rel+2/(df+3))/(rel+1) if np.isfinite(rel) else 1)
def effects(a):
    a['interaction_percent']=100*np.expm1(a['beta']);a['CI_percent_lower']=100*np.expm1(a['beta_CI_lower']);a['CI_percent_upper']=100*np.expm1(a['beta_CI_upper']);return a
def run():
    cfg=json.loads((O/'config.json').read_text());e,c,p,draws,z=r.load();rows=[];checks=[];marg=[]
    for j in cfg['jobs']:
        path=O/'checkpoints'/f"{j['task_id']}.json"
        a=json.loads(path.read_text()) if path.exists() else {**j,'fit_status':'not_run','failure_reason':'checkpoint absent'}
        fits=a.pop('fits',[])
        if a['fit_status']=='completed':
            per=pd.DataFrame(fits);v=independent_pool(per.interaction_beta,per.interaction_variance)
            error=max(abs(a[k]-v[k]) for k in ['beta','SE','beta_CI_lower','beta_CI_upper','P_value','total_variance'])
            checks.append(dict(check='independent_pool',task_id=j['task_id'],passed=error<1e-10,error=error))
            assert error<1e-10
            for k,val in effects(v).items():a[k]=val
            if j['analysis_block']=='A':
                for s in range(-2,3):
                    variance=per.exposure_variance+s*s*per.interaction_variance+2*s*per.exposure_interaction_covariance
                    v=independent_pool(per.exposure_beta+s*per.interaction_beta,variance)
                    b={**a,**effects(v),'analysis_block':'B','contrast_id':f'SES_{s:+d}','ses_sd':s,'within_observed_support':a['ses_min']<=s<=a['ses_max'],'exposure_unit':'per fixed smoke IQR at specified baseline SES'}
                    marg.append(b)
                    pd.DataFrame(dict(imputation=per.imputation,log_contrast=per.exposure_beta+s*per.interaction_beta,within_variance=variance)).to_csv(O/'per_imputation'/f"{j['task_id']}__SES_{s:+d}.csv",index=False)
        elif j['analysis_block']=='A':
            for s in range(-2,3):marg.append({**a,'analysis_block':'B','contrast_id':f'SES_{s:+d}','ses_sd':s,'fit_status':'blocked','failure_reason':'reference model not completed'})
        rows.append(a)
    df=pd.DataFrame(rows+marg)
    df['P_adjusted']=np.nan;df['comparison_family']=None
    ids=df.index[df.analysis_block.eq('A')];assert len(ids)==7
    raw=df.loc[ids,'P_value'].to_numpy(float); adj=multipletests(np.where(np.isfinite(raw),raw,1),method='holm')[1];adj[~np.isfinite(raw)]=np.nan
    df.loc[ids,'P_adjusted']=adj;df.loc[ids,'comparison_family']='A_seven_reference_interactions_Holm'
    df['percent_estimate']=df.interaction_percent;df['percent_CI_lower']=df.CI_percent_lower;df['percent_CI_upper']=df.CI_percent_upper
    for field in ['contrast_id','formula','exposure_unit','imputation_version','sample_hash','year_min','year_max','n_counties','n_states','n_county_years','beta','SE','beta_CI_lower','beta_CI_upper','P_value','n_imputations','within_variance','between_imputation_variance','df_rubin','run_source','source_path','run_fingerprint']:
        if field not in df:df[field]=np.nan
    df['missing_value_definition']='blank=not applicable or unavailable; see fit_status/failure_reason'
    for k in ['dropped_aliases']:
        if k in df:df[k]=df[k].map(lambda a:json.dumps(a) if isinstance(a,list) else a)
    df.to_csv(O/'AFIRE_7outcome_all_results.csv',index=False)
    blocks={'primary_7outcomes':'A','marginal_associations_7outcomes':'B','common_sample_7outcomes':'C','targeted_omissions_7outcomes':'D','LST_paired_7outcomes':'E'}
    for name,b in blocks.items():df[df.analysis_block.eq(b)].to_csv(O/(name+'.csv'),index=False)
    primary=df[df.analysis_block.eq('A')].copy();primary.to_csv(O/'primary_multiplicity_7outcomes.csv',index=False)
    diags=[]
    for a in rows:
        j=next(j for j in cfg['jobs'] if j['task_id']==a['task_id']);s=r.subset(j,c,p); sup=e.bool_series(s.death_suppressed).to_numpy();y=draws[:,s.draw_column]
        diags.append({**a,'diagnostic_year_scope':'model sample','n_public_zero':int(s.deaths.eq(0).sum()),'public_zero_fraction':float(s.deaths.eq(0).mean()),'n_suppressed':int(sup.sum()),'suppression_fraction':float(sup.mean()),'hidden_death_fraction':float(y[:,sup].sum()/y.sum()),'mean_hidden_deaths':float(y[:,sup].sum(axis=1).mean()),'MC_error_over_SE':a.get('monte_carlo_error',np.nan)/a.get('SE',np.nan)})
    diagnostics=pd.DataFrame(diags);diagnostics.to_csv(O/'diagnostics_7outcomes.csv',index=False)
    coverage=df[['outcome_id','analysis_block','model_id','contrast_id','fit_status','n_imputations','source_path']].copy()
    coverage=pd.concat([coverage,pd.DataFrame([dict(outcome_id=a,analysis_block='F',model_id='Holm_and_diagnostics',fit_status='completed' if primary.fit_status.eq('completed').all() else 'partial') for a in r.CAUSES])],ignore_index=True)
    coverage.to_csv(O/'analysis_coverage_after.csv',index=False)
    # Exact keys, across outcomes and all common models; all four LST pairs.
    common=df[df.analysis_block.eq('C')]
    checks.append(dict(check='common_all_outcomes_same_sample',passed=common.sample_hash.nunique()==1 and len(common)==56))
    for (cause,base,qa),g in df[df.analysis_block.eq('E')].assign(base=lambda x:x.model_id.str.split('_').str[0],qa=lambda x:x.model_id.str.split('_').str[1]).groupby(['outcome_id','base','qa']):
        checks.append(dict(check='LST_pair_keys',task_id=f'{cause}_{base}_{qa}',passed=len(g)==2 and g.sample_hash.nunique()==1))
    checks.append(dict(check='seven_reference_same_sample',passed=primary.sample_hash.nunique()==1))
    changes=[]
    for cause in r.CAUSES:
        d=df[df.outcome_id.eq(cause)];a=d[d.analysis_block.eq('A')].iloc[0];cm=d[d.analysis_block.eq('C')].set_index('model_id')
        changes.append(dict(outcome_id=cause,comparison='reference_to_common_M2',kind='sample restriction only',beta_change=cm.loc['M2','beta']-a.beta,n_before=a.n_county_years,n_after=cm.loc['M2','n_county_years']))
        for before,after in [('M0','M1'),('M1','M2'),('M2','M2P'),('M2','M3'),('M3','M3L'),('M3','M3P_joint'),('M3P_joint','M3PL_joint')]:
            changes.append(dict(outcome_id=cause,comparison=before+'_to_'+after,kind='covariate adjustment on identical sample',beta_change=cm.loc[after,'beta']-cm.loc[before,'beta'],n_before=cm.loc[before,'n_county_years'],n_after=cm.loc[after,'n_county_years']))
        for qa in ['relaxed','strict']:
            for base in ['M2','M3']:
                pair=d[d.analysis_block.eq('E')].set_index('model_id');a0=pair.loc[f'{base}_{qa}_noLST'];a1=pair.loc[f'{base}_{qa}_withLST']
                changes.append(dict(outcome_id=cause,comparison=f'{base}_{qa}_LST_addition',kind='LST variable on paired sample',beta_change=a1.beta-a0.beta,n_before=a0.n_county_years,n_after=a1.n_county_years))
                ref=a if base=='M2' else cm.loc['M3']
                changes.append(dict(outcome_id=cause,comparison=f'{base}_{qa}_selection',kind='sample selection only',beta_change=a0.beta-ref.beta,n_before=ref.n_county_years,n_after=a0.n_county_years))
    pd.DataFrame(changes).to_csv(O/'source_data/sample_vs_adjustment_changes.csv',index=False)
    # Recompute LST eligibility directly from preserved monthly coverage.
    lst=pd.read_csv(r.ROOT/c['inputs']['LST_panel']);lst=lst[lst.period.eq('day')]
    expected=lst.coverage.ge(.7)
    for m in range(5,11):expected &= lst[f'coverage_m{m:02d}'].ge(.5)&lst[f'LST_C_m{m:02d}'].notna()
    checks.append(dict(check='LST_eligibility_recalculated_monthly',passed=bool((expected==e.bool_series(lst.eligible_s070)).all())))
    # Explicit shuffle check establishes row_id alignment independent of input order.
    perm=np.random.default_rng(7301).permutation(len(z['row_ids'])); mapping=pd.Series(np.arange(len(perm)),index=z['row_ids'][perm]);reordered=z['draws'][:,perm][:,mapping.loc[p.row_id].to_numpy()]
    checks.append(dict(check='imputation_shuffled_key_alignment',passed=bool(np.array_equal(reordered,draws))))
    freeze=json.loads((O/'audit/freeze_hashes.json').read_text())
    for path,h in freeze.items():checks.append(dict(check='frozen_hash_'+path,passed=r.sha(O/path)==h))
    checks.append(dict(check='mandatory_model_status_complete',passed=len(rows)==154 and all(a['fit_status']=='completed' and a.get('n_imputations')==30 for a in rows)))
    pd.DataFrame(checks).to_csv(O/'audit/independent_validation.csv',index=False)
    figures(df)
    reports(df,diagnostics,checks)
    print('TABLES AND FIGURES EXPORTED',len(df),'rows',flush=True)
def figures(df):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','pdf.fonttype':42})
    labels=['COPD','Chronic lower respiratory','Respiratory system','Circulatory system','Ischemic heart disease','Asthma','Cerebrovascular disease']
    for block,stem in [('A','primary_interaction'),('B','marginal_associations'),('C','common_environment'),('D','targeted_omissions'),('E','LST_pairs')]:
        d=df[df.analysis_block.eq(block)];d.to_csv(O/'source_data'/f'{stem}.csv',index=False)
        if block=='A':
            fig,ax=plt.subplots(figsize=(8,4.6)); axes=[ax]
            for i,cause in enumerate(r.CAUSES):
                q=d[d.outcome_id.eq(cause)].iloc[0]
                if q.fit_status=='completed':ax.errorbar(q.percent_estimate,i,xerr=[[q.percent_estimate-q.percent_CI_lower],[q.percent_CI_upper-q.percent_estimate]],fmt='o',color='#236A8A',capsize=3)
                else:ax.text(0,i,'FAILED',color='#A33')
            ax.set_yticks(range(7),labels);ax.invert_yaxis();ax.axvline(0,color='.6',lw=.7);ax.set_xlabel('Interaction: rate-ratio ratio change (%) per smoke IQR × SES SD')
        else:
            fig,axs=plt.subplots(4,2,figsize=(13,15 if block in ['C','E'] else 12));axes=list(axs.flat)
            for i,cause in enumerate(r.CAUSES):
                ax=axes[i];g=d[d.outcome_id.eq(cause)].reset_index(drop=True);ax.set_title(labels[i],loc='left');ax.axvline(0,color='.65',lw=.7)
                for k,q in g.iterrows():
                    if q.fit_status=='completed':
                        color='#236A8A' if block!='B' or q.within_observed_support else '#A33'
                        ax.errorbar(q.percent_estimate,k,xerr=[[q.percent_estimate-q.percent_CI_lower],[q.percent_CI_upper-q.percent_estimate]],fmt='o',color=color,capsize=2,ms=4)
                    else:ax.text(0,k,'FAILED',color='#A33')
                names=g.contrast_id if block=='B' else g.model_id
                ax.set_yticks(range(len(g)),names);ax.invert_yaxis();ax.set_xlabel('Smoke association (%)' if block=='B' else 'Smoke × SES interaction (%)')
            axes[-1].axis('off')
        for ax in axes:ax.spines[['top','right']].set_visible(False)
        fig.tight_layout()
        for ext in ['png','svg','pdf']:fig.savefig(O/'figures'/f'{stem}.{ext}',dpi=220,bbox_inches='tight')
        plt.close(fig)
    (O/'figures/CAPTIONS.md').write_text('''所有图结局顺序固定。点为30份fixed EB 1–9插补的Rubin合并估计，线为普通双侧95%区间，不是Holm同时区间。烟霾单位为固定IQR=0.678107947271523 μg/m³；SES正向为更不利，每1 SD。各点精确样本规模、键哈希、P值和状态见同名 source_data CSV。

分面横轴范围独立，以保留哮喘等宽区间的可读性；跨结局比较应阅读横轴数值，不能按线段视觉长度比较精度。

primary_interaction：七结局参考M2（2009–2020）交互，主要七检验家族校正P值见primary_multiplicity表。交互百分比是率比之比的变化。
marginal_associations：SES −2至+2 SD的烟霾边际关联；每份插补使用烟霾和交互的完整2×2协方差构造后合并。超出观测范围的点为红色，不能作为经验结论。
common_environment：共同样本八模型，M2P为降水独立分支，M3不包含降水。样本变化与调整变化另见sample_vs_adjustment_changes.csv。
targeted_omissions：完整样本、删2020、删CA、同时删CA及2020、仅删CA在2020的行；固定暴露及SES尺度。
LST_pairs：M2/M3基础模型、strict/relaxed昼间质量分支，无/有LST逐对同键。LST单位每10°C，为地表温度；跨质量分支差异不能全归因于LST变量调整。
''',encoding='utf-8')
def fmt(q):
    return f"{q.percent_estimate:.4f}%（95%区间 {q.percent_CI_lower:.4f} 至 {q.percent_CI_upper:.4f}；P={q.P_value:.5g}）" if q.fit_status=='completed' else f"未完成：{q.get('failure_reason','未知')}"
def reports(df,diag,checks):
    lines=['# 七个死亡结局统一扩展结果','', '本报告是已有结果基础上的后续扩展分析。七种嵌套死因的县—年死亡关联不能相加，亦不是七次独立验证。','', '## 参考主模型与Holm校正','']
    primary=df[df.analysis_block.eq('A')]
    significant=primary[primary.P_adjusted.lt(.05)].outcome_name.tolist()
    other=primary[~primary.P_adjusted.lt(.05)].outcome_name.tolist()
    bm=df[df.analysis_block.eq('B')]
    positive=int(bm.percent_CI_lower.gt(0).sum());negative=int(bm.percent_CI_upper.lt(0).sum());uncertain=int((bm.percent_CI_lower.le(0)&bm.percent_CI_upper.ge(0)).sum())
    lines[4:4]=['## 主要发现','',f"七检验Holm校正后P<0.05：{'、'.join(significant) or '无'}；其余：{'、'.join(other) or '无'}。这不是疾病间效应差异检验。",f"35个预定SES边际对比中，普通95%区间完全为正{positive}个、完全为负{negative}个、跨0共{uncertain}个。这些区间未作同时校正，负关联不作保护效应解释。",'']
    for cause,name in zip(r.CAUSES,r.NAMES):
        q=df[df.outcome_id.eq(cause)&df.analysis_block.eq('A')].iloc[0];lines.append(f'- {name}：交互 {fmt(q)}；Holm P={q.P_adjusted:.5g}；{q.n_county_years:.0f}县—年、{q.n_counties:.0f}县、{q.n_states:.0f}州。')
    lines+=['','## 边际烟霾关联','']
    for cause,name in zip(r.CAUSES,r.NAMES):
        d=df[df.outcome_id.eq(cause)&df.analysis_block.eq('B')];ss=[]
        for _,q in d.iterrows():
            typ='正向区间' if q.percent_CI_lower>0 else ('负向区间' if q.percent_CI_upper<0 else '区间跨0，方向不确定')
            ss.append(f"SES {q.ses_sd:+.0f}：{fmt(q)}，{typ}"+('，超出支持范围' if not q.within_observed_support else ''))
        lines.append(f"- {name}："+'；'.join(ss)+'。')
    lines+=['','正交互表示随SES劣势增加烟霾关联向更正方向移动，不等同于死亡增加；负边际关联不能解释为保护作用。','', '## 环境调整、删除与LST配对','']
    for cause,name in zip(r.CAUSES,r.NAMES):
        d=df[df.outcome_id.eq(cause)];cm=d[d.analysis_block.eq('C')];de=d[d.analysis_block.eq('D')];lst=d[d.analysis_block.eq('E')]
        lines+=['',f'### {name}','', '共同样本（逐结局八模型同键）：'+'；'.join(f'{q.model_id} {fmt(q)}' for _,q in cm.iterrows())+'。', '', '定向删除：'+'；'.join(f'{q.model_id} [n={q.n_county_years:.0f}] {fmt(q)}' for _,q in de.iterrows())+'。','']
        for qa in ['relaxed','strict']:
            for base in ['M2','M3']:
                pair=lst.set_index('model_id');a=pair.loc[f'{base}_{qa}_noLST'];b=pair.loc[f'{base}_{qa}_withLST'];lines.append(f'- {base}/{qa}：{a.n_county_years:.0f}县—年、{a.n_counties:.0f}县、{a.n_states:.0f}州；无LST {fmt(a)}；加LST {fmt(b)}。')
    lines+=['','以上变化均为描述：样本筛选效应与同键协变量调整分开记录于source_data/sample_vs_adjustment_changes.csv。删除后点估计为正不代表显著稳健，调整变化小不证明等效或已消除混杂。','', '## 抑制与重建不确定性','']
    sensitivity=[]
    for cause,name in zip(r.CAUSES,r.NAMES):
        d=df[df.outcome_id.eq(cause)];a=d[d.analysis_block.eq('A')].iloc[0];de=d[d.analysis_block.eq('D')&d.model_id.ne('full')].copy()
        de['absolute_beta_shift']=abs(de.beta-a.beta);big=de.loc[de.absolute_beta_shift.idxmax()]
        crosses=de[de.percent_CI_lower.le(0)&de.percent_CI_upper.ge(0)].model_id.tolist()
        reverses=de[de.beta*a.beta<0].model_id.tolist()
        sensitivity.append(f"- {name}：最大点估计变化出现在{big.model_id}（log交互变化{big.beta-a.beta:+.6f}）；删除后区间跨0：{', '.join(crosses) or '无'}；点估计变号：{', '.join(reverses) or '无'}。这些标记仅帮助阅读，所有删除均保留。")
    lines[-3:-3]=['','### 定向删除敏感性阅读索引','']+sensitivity
    for _,q in diag[diag.analysis_block.eq('A')].iterrows():lines.append(f"- {q.outcome_name}：公开零{q.n_public_zero}；抑制比例{q.suppression_fraction:.2%}；隐藏死亡比例{q.hidden_death_fraction:.2%}；插补间方差{q.between_imputation_variance:.5g}；FMI={q.fraction_missing_information:.5g}；beta Monte Carlo标准误={q.monte_carlo_error:.5g}（总SE的{q.MC_error_over_SE:.2%}）；alpha={q.dispersion_alpha:.5g}，触及截断边界={q.alpha_at_bound}。")
    lines+=['','## 不能支持的结论','', '不能据一项显著另一项不显著认定疾病间效应不同；未估计嵌套结局联合协方差。普通95%区间未作同时校正。县聚类没有覆盖跨县相关性。死亡查询同批次及完整过滤条件不足；1–9为本轮保持的B1条件，不把历史文件名当作批次证据。固定EB权重估计不确定性未传播。SES上游完整组件权重溯源尚未闭合。未新增机制、因果、超额死亡或全国人口加权暴露结论。']
    (O/'RESULTS_SUMMARY_CN.md').write_text('\n'.join(lines),encoding='utf-8')
    passed=sum(bool(x['passed']) for x in checks)
    (O/'AUDIT_REPORT.md').write_text(f'''# 独立核查报告

本轮154个模型任务、35个边际对比；全部任务状态见analysis_coverage_after.csv。当前模型完成{int(df[df.analysis_block.ne('B')].fit_status.eq('completed').sum())}/154；独立核查通过{passed}/{len(checks)}。核查失败不得称为验收通过。

原始归档县死亡、州总量与面板逐键核对；30份插补公开零/正计数保持、1–9整数支持、州—年—死因总量全部精确检查，详见audit。随机打乱插补列后依row_id恢复并逐值比较。COPD和慢性下呼吸道疾病入口一致性见entry_consistency.csv。未复用旧模型估计；每个任务重建离散参数，30/30才合并。D完整样本与A及同样本LST基础模型重复拟合是审计冗余，未重复计入Holm家族。

每份插补保存完整烟霾/交互2×2协方差所需三个元素，边际对比在插补内构造。独立实现Rubin合并并核对beta、SE、区间、P及方差；Holm固定家族7。缓存含输入、代码、配置及样本指纹。

SES观测支持、设计秩/列数/条件数、逐模型alpha及边界标记、收敛、插补不确定性和MC标准误均输出。完整共同样本跨结局同键、LST每对同键检查，不以历史样本数强行裁剪。排除县—年及州详见sample_keys/*__excluded.csv。

LST按现有v3产品复算月/季覆盖资格。已读QC位和仅配对LST有效时恢复QC=0的实现及既有源像元证据；没有重新下载卫星数据，不能扩大旧像元核验的代表性。

当前没有适用目录下AGENTS.md；已读last/AGENTS.md和PROJECT_STATUS.md，其余两份启动文档未在last找到，且本任务不修改论文。nature-statistics/nature-figure不可用，未安装。无可读Git工作树，以全部原文件SHA256替代版本及保护核查。未修改公共代码，复用引擎按字节快照。模型环境为原项目.venv；XLSX用已有系统openpyxl单独导出，不安装依赖、不混用统计环境。

来源缺口、方法扩展优先级见audit/provenance_and_future.md；原文件最终哈希核查见audit/original_files_after.csv。输出清单与最终验收状态见audit/delivery_validation.json。
''',encoding='utf-8')
    (O/'README.md').write_text('''# AFIRE 七结局统一扩展

总结果：AFIRE_7outcome_all_results.csv；Excel：AFIRE_7outcome_results.xlsx。中文结果见RESULTS_SUMMARY_CN.md，核查见AUDIT_REPORT.md。配置和协议先冻结，全部结果局限本目录；空白字段为不适用或不可计算，不等于0。

复现：在项目根目录用 experiment_longrun_20260906/.venv/bin/python 本目录/run_extension.py models 断点续跑；随后同环境执行deliver.py，系统python执行export_xlsx.py。不要再次运行audit以覆盖冻结配置。所有模型30份，不允许部分合并。最终核查执行final_check.py。

figures内有可编辑SVG/PDF和PNG，图注及source_data配套。sample_keys有每任务样本及排除键，per_imputation保存逐份估计和协方差，checkpoints/logs保存指纹及任务状态。所有结局顺序固定。A七参考交互为唯一主要Holm家族，B–E均为解释性或敏感性分析。
''',encoding='utf-8')
if __name__=='__main__':run()
