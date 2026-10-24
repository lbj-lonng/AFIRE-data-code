#!/usr/bin/env python3
"""Isolated seven-outcome B1 extension; no historical entry point is executed."""
import os
from pathlib import Path
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[k] = '1'
os.environ['MPLCONFIGDIR'] = str(OUT/'cache/matplotlib')
os.environ['PYTHONPYCACHEPREFIX'] = str(OUT/'cache/pycache')
import sys, json, hashlib, shutil, time, traceback, argparse, platform
sys.dont_write_bytecode = True
import importlib.util
import numpy as np
import pandas as pd
from scipy.stats import t, norm
from concurrent.futures import ProcessPoolExecutor, as_completed
OLD = ROOT/'analysis/AFIRE_B1_joint_adjustment_20260909_233833'
SOURCE = OUT/'code_snapshot/b1_engine.py'
CAUSES = ['copd','chronic_lower_respiratory','respiratory_system','circulatory_system','ischemic_heart_disease','asthma','cerebrovascular_disease']
NAMES = ['慢性阻塞性肺疾病','慢性下呼吸道疾病','呼吸系统疾病','循环系统疾病','缺血性心脏病','哮喘','脑血管疾病']
ICD = ['J40-J44','J40-J47','J00-J98','I00-I99','I20-I25','J45-J46','I60-I69']
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def js(p,d):
    p=Path(p); tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str)); tmp.replace(p)
def engine():
    spec=importlib.util.spec_from_file_location('b1_engine',SOURCE); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m
def setup():
    for d in ['figures','source_data','per_imputation','sample_keys','logs','code_snapshot','audit','cache','checkpoints']:(OUT/d).mkdir(exist_ok=True,parents=True)
    if not SOURCE.exists():shutil.copy2(OLD/'run_pipeline.py',SOURCE)
def load():
    e=engine(); c=json.loads((OLD/'00_protocol/config.json').read_text()); c['output_root']=str(OUT)
    p=e.load_prepared_panel(c)
    z=np.load(OLD/'tmp/fixed_EB_B1_1_9_all_outcomes_30.npz')
    ids=z['row_ids'].astype(int); assert len(set(ids))==len(ids)
    # Explicit row_id mapping, including when file order differs from panel order.
    ix=pd.Series(np.arange(len(ids)),index=ids).loc[p.row_id].to_numpy()
    draws=z['draws'][:,ix].astype(float)
    p['draw_column']=np.arange(len(p))
    lst=pd.read_csv(ROOT/c['inputs']['LST_panel']); lst=lst[lst.period.eq('day')]
    for qa in ['strict','relaxed']:
        q=lst[lst.QA_rule.eq(qa)].copy(); q['county_fips']=q.FIPS.astype(int)
        assert not q.duplicated(['county_fips','year']).any()
        q=q.set_index(['county_fips','year']); index=pd.MultiIndex.from_frame(p[['county_fips','year']])
        p[qa+'_lst']=index.map(q.LST_C)/10
        p[qa+'_eligible']=index.map(e.bool_series(q.eligible_s070)).fillna(False).astype(bool)
    return e,c,p,draws,z
def requirements(formula):
    return list(dict.fromkeys(['pm25_iqr','ses_baseline_std']+[s.strip() for s in formula.split('+') if ':' not in s and 'C(' not in s]))
def tasks(c,p):
    jobs=[]
    for cause in CAUSES:
        for block,mid,f,mode in [('A','reference',c['formulas']['M2'],'reference')]+[('C',m,f,'common') for m,f in c['formulas'].items()]+[('D',m,c['formulas']['M2'],m) for m in ['full','drop2020','dropCA','dropCA_and2020','dropCA2020only']]+[('E',f'{base}_{qa}_{added}',c['formulas'][base]+(' + day_LST_per10' if added=='withLST' else ''),qa) for base in ['M2','M3'] for qa in ['relaxed','strict'] for added in ['noLST','withLST']]:
            jobs.append(dict(outcome_id=cause,outcome_name=NAMES[CAUSES.index(cause)],analysis_block=block,model_id=mid,formula=f,mode=mode,task_id=f'{cause}__{block}__{mid}'))
    return jobs
def subset(j,c,p):
    s=p[p.cause_id.eq(j['outcome_id']) & p.year.between(2009,2020)].copy()
    req=requirements(j['formula']); mode=j['mode']
    if mode=='common':
        req=requirements(c['formulas']['M3PL_joint']); s=s[s.relaxed_eligible]
    if mode in ['strict','relaxed']:
        s['day_LST_per10']=s[mode+'_lst']; s=s[s[mode+'_eligible'] & s.day_LST_per10.notna()]
    if mode in ['drop2020','dropCA_and2020']:s=s[s.year.ne(2020)]
    if mode in ['dropCA','dropCA_and2020']:s=s[s.state_abbr.ne('CA')]
    if mode=='dropCA2020only':s=s[~(s.state_abbr.eq('CA') & s.year.eq(2020))]
    return s.dropna(subset=req+['population']).loc[lambda x:x.population.gt(0)].sort_values(['county_fips','year']).reset_index(drop=True)
def audit():
    setup(); e,c,p,d,z=load()
    sources=[(str(path.relative_to(ROOT)),path) for path in ROOT.rglob('*') if path.is_file() and OUT.parent not in path.parents and not any(x in path.parts for x in ['.venv','__pycache__','.git'])]
    # Protect all existing project artifacts, not merely selected model inputs.
    pd.DataFrame([dict(path=str(v),size=v.stat().st_size,sha256=sha(v)) for _,v in sources]).to_csv(OUT/'audit/original_files_before.csv',index=False)
    query=ROOT/'experiment_feasibility_20260906/source_snapshot/all/03/data_raw/health_state/query_scope.json'
    mapping={x['cause_id']:x['icd10'] for x in json.loads(query.read_text())['causes']}
    assert all(mapping[a]==b for a,b in zip(CAUSES,ICD))
    raw,checks=e.reconcile_raw_mortality(c,p); raw.to_csv(OUT/'audit/raw_mortality_reconciliation.csv',index=False); pd.DataFrame(checks).to_csv(OUT/'audit/raw_checks.csv',index=False)
    assert all(x['passed'] for x in checks)
    assert d.shape==(30,len(p)) and np.isfinite(d).all() and np.equal(d,np.floor(d)).all()
    integ=[]
    for cause in CAUSES:
        s=p[p.cause_id.eq(cause)]; a=d[:,s.draw_column]; sup=e.bool_series(s.death_suppressed).to_numpy()
        err=max(float(np.abs(d[:,g.draw_column].sum(axis=1)-g.state_deaths.iloc[0]).max()) for _,g in s.groupby(['state_abbr','year']))
        public=bool((a[:,~sup]==s.deaths.to_numpy()[~sup]).all()); bounds=bool(((a[:,sup]>=1)&(a[:,sup]<=9)).all())
        assert public and bounds and err==0
        integ.append(dict(outcome_id=cause,n_rows=len(s),n_public_zero=int(s.deaths.eq(0).sum()),suppression_fraction=float(sup.mean()),hidden_death_fraction=float(a[:,sup].sum()/a.sum()),public_unchanged=public,bounds_1_9=bounds,state_total_max_error=err))
    pd.DataFrame(integ).to_csv(OUT/'audit/imputation_integrity.csv',index=False)
    smoke=next(k for k in ['county_smoke_pm25_annual_burden_y','county_smoke_pm25_annual_burden_x','county_smoke_pm25_annual_burden'] if k in p)
    ratio=p.loc[p.pm25_iqr.ne(0),smoke]/p.loc[p.pm25_iqr.ne(0),'pm25_iqr']
    assert np.allclose(ratio,0.678107947271523,rtol=0,atol=1e-10)
    assert p.groupby('county_fips').ses_baseline_std.nunique().max()==1
    js(OUT/'audit/scales.json',dict(iqr=float(ratio.median()),max_scale_error=float(abs(ratio-ratio.median()).max()),ses_min=float(p.ses_baseline_std.min()),ses_max=float(p.ses_baseline_std.max()),seed_map=json.loads(z['seed_map_json'][0])))
    jobs=tasks(c,p); cov=[]
    for j in jobs:
        s=subset(j,c,p); key=s[['row_id','cause_id','county_fips','state_abbr','year']]; key.to_csv(OUT/'sample_keys'/f"{j['task_id']}.csv",index=False)
        base=p[p.cause_id.eq(j['outcome_id']) & p.year.between(2009,2020)]
        exc=base[~base.row_id.isin(s.row_id)][['row_id','county_fips','state_abbr','year']].copy(); exc['reason']='prespecified '+j['mode']+' selection or required covariate missing'; exc.to_csv(OUT/'sample_keys'/f"{j['task_id']}__excluded.csv",index=False)
        oldname='O10_temperature_adjusted_2009_2020' if j['outcome_id']=='copd' else 'D_'+j['outcome_id']
        candidate=OLD/'03_model_fits/checkpoints'/f'{oldname}.json' if j['analysis_block']=='A' else None
        cov.append({**j,'n_county_years':len(s),'sample_hash':e.key_hash(s),'status':'needs_recalculation','existing_candidate':str(candidate) if candidate and candidate.exists() else None,'decision':'refit all; historical results used only for numerical consistency checks'})
    coverage=pd.DataFrame(cov)
    marg=[dict(outcome_id=a,analysis_block='B',model_id='reference',contrast_id=f'SES_{v:+d}',status='needs_recalculation',decision='requires within-imputation covariance') for a in CAUSES for v in range(-2,3)]
    frows=[dict(outcome_id=a,analysis_block='F',model_id='primary_Holm_and_diagnostics',status='needs_recalculation') for a in CAUSES]
    pd.concat([coverage,pd.DataFrame(marg+frows)],ignore_index=True).to_csv(OUT/'analysis_coverage_before.csv',index=False)
    config=dict(protocol_version='7outcome_extension_v1',frozen_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),project_root=str(ROOT),output_root=str(OUT),outcomes=[dict(outcome_id=a,outcome_name=b,icd10=i) for a,b,i in zip(CAUSES,NAMES,ICD)],years=[2009,2020],formulas=c['formulas'],imputations=30,imputation_version='fixed_EB_B1_1_9',seed_map=json.loads(z['seed_map_json'][0]),smoke_iqr=float(ratio.median()),ses='existing fixed baseline disadvantage, positive=higher disadvantage; no restandardization',workers=2,threads=1,main_family='seven reference interaction two-sided P values; Holm family size fixed at seven',marginal_SES=[-2,-1,0,1,2],tolerance=dict(beta_abs=1e-8,variance_abs=1e-10,counts_abs=0),fit_rules='original NB maxiter=200 tol=1e-8; retry maxiter=500 tol=1e-7 exactly as existing B1; no additional relaxation; 30/30 mandatory',pooling='original Rubin t df=(m-1)(1+1/r)^2; no Barnard-Rubin df; county sandwich G/(G-1)*(N-1)/(N-K)',alpha='per outcome per model Poisson on mean imputed counts, moment alpha clipped [0.001,2], then fixed for 30 NB fits',jobs=jobs,input_hashes={k:sha(ROOT/v) for k,v in c['inputs'].items() if (ROOT/v).is_file()},draw_sha256=sha(OLD/'tmp/fixed_EB_B1_1_9_all_outcomes_30.npz'),engine_sha256=sha(SOURCE),entry_sha256=sha(Path(__file__)))
    js(OUT/'config.json',config)
    (OUT/'protocol_frozen.md').write_text('''# 七结局统一扩展协议

这是基于已有结果制定的后续扩展方案，不是原始研究前瞻性预注册。具体结局编码、公式、种子、输入哈希和全部任务固定在 config.json；样本键在 sample_keys。所有模型重新拟合，旧结果仅用于一致性测试。

A：七结局2009–2020 M2/O10参考模型。B：每份插补以完整2×2烟霾/交互协方差计算SES −2至+2的线性对比，再Rubin合并；范围外标记。C：八个共同样本模型，M2P为独立分支，M3不包含降水；样本要求M3PL全部变量和relaxed day资格。D：全样本及四种预定删除。E：M2/M3 × relaxed/strict day × 无/有LST，逐对固定样本。F：七个A交互为固定Holm家族；失败保留缺失，校正计算内部按1占位但不报告为观测P。B–E为解释性与敏感性分析；普通95%区间不是同时区间。

保持县/年固定效应、log人口offset、县聚类有限样本修正、原B1逐模型alpha及Rubin规则。固定SES主效应不纳入。30份全部成功才合并。重试精确沿用原B1规则（200/1e-8，随后500/1e-7），不进一步降低标准。缓存签名包含结局、公式、样本、插补、配置、代码；失败逐份记录。COPD和慢性下呼吸道疾病先跑30份并与旧入口结果比较，容差beta 1e-8、方差1e-10；失败阻断批量。

LST沿用MOD11A2.061 5–10月昼间面积—时间加权，每10摄氏度。strict要求QC bits0–1=0, bits2–3=0, bits6–7=0；relaxed要求bits0–1≤1, bits6–7≤1。季节覆盖≥0.70、6个月均有值、每月覆盖≥0.50。QC缺失仅在配对LST有效处恢复0；沿用v3产品及既有源像元核验，未重新下载。LST不是气温或个体热暴露。

保持结局固定顺序，不按显著性选择分析。正交互不是正向边际关联或超额死亡；负关联不是保护效应。结局嵌套不可相加，不构成独立验证，不估计疾病间正式差异。系数变化为描述，不能证明等效、无混杂或机制。

上游SES完整权重来源、死亡查询批次版本、fixed EB权重依据及未覆盖的跨县相关性单独保留为来源/推断缺口；可在现有固定面板和权重条件下复现下游。全国人口权重不在范围。层级EB、模拟校准、跨县推断、滞后及非线性本轮只审查，不新增搜索。
''',encoding='utf-8')
    js(OUT/'audit/freeze_hashes.json',{k:sha(OUT/k) for k in ['config.json','protocol_frozen.md','run_extension.py','code_snapshot/b1_engine.py']})
    import statsmodels,scipy,matplotlib
    js(OUT/'audit/environment.json',dict(python=sys.version,executable=sys.executable,platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,statsmodels=statsmodels.__version__,matplotlib=matplotlib.__version__,git='not a git repository; full original file hashes recorded',nature_skills='nature-statistics and nature-figure unavailable; no installation'))
    print('FROZEN',len(jobs),'model tasks',flush=True)
def fit(j):
    e,c,p,d,z=load(); s=subset(j,c,p); path=OUT/'checkpoints'/f"{j['task_id']}.json"
    cfg=json.loads((OUT/'config.json').read_text())
    signature=hashlib.sha256(json.dumps([j,e.key_hash(s),cfg['draw_sha256'],sha(OUT/'config.json'),sha(SOURCE),sha(Path(__file__))],sort_keys=True).encode()).hexdigest()
    old=json.loads(path.read_text()) if path.exists() else {}
    if old.get('run_fingerprint')==signature and old.get('fit_status')=='completed':return old
    r={**j,'contrast_id':'interaction','run_fingerprint':signature,'sample_hash':e.key_hash(s),'n_county_years':len(s),'n_counties':s.county_fips.nunique(),'n_states':s.state_abbr.nunique(),'states':','.join(sorted(s.state_abbr.unique())),'year_min':int(s.year.min()),'year_max':int(s.year.max()),'imputation_version':'fixed_EB_B1_1_9','exposure_unit':'per 0.678107947271523 ug/m3 smoke and per 1 SD disadvantage','run_source':'recomputed','source_path':str(path),'fit_status':'running','n_imputations':0,'ses_min':float(s.ses_baseline_std.min()),'ses_max':float(s.ses_baseline_std.max())}
    per=[]; started=time.time()
    try:
        job=e.Job(j['task_id'],j['analysis_block'],j['outcome_id'],'negative_binomial',j['formula'],e.EXPOSURE,e.TERM,tuple(requirements(j['formula'])),2009,2020)
        x,names,idx,norig,dropped=e.build_design(s,job); yy=d[:,s.draw_column]; offset=np.log(s.population.to_numpy()); groups=s.county_fips.to_numpy()
        alpha,warm=e.estimate_nb_alpha(yy.mean(axis=0),x,offset)
        r.update(design_rank=int(np.linalg.matrix_rank(x)),design_columns=x.shape[1],original_design_columns=norig,dropped_aliases=dropped,dispersion_alpha=alpha,alpha_at_bound=bool(alpha in [0.001,2.0]),design_condition_number=float(np.linalg.cond(x)))
        prev=old.get('fits',[]) if old.get('run_fingerprint')==signature else []
        for m,y in enumerate(yy,1):
            cached=next((v for v in prev if v['imputation']==m and v['status']=='ok'),None)
            if cached:per.append(cached);continue
            try:
                result,est=e.fit_one(y,x,offset,groups,'negative_binomial',alpha,warm); b=np.asarray(result.params); v=np.asarray(result.cov_params()); ei=idx[e.EXPOSURE]; ii=idx[e.TERM]
                per.append(dict(imputation=m,status='ok',exposure_beta=float(b[ei]),interaction_beta=float(b[ii]),exposure_variance=float(v[ei,ei]),interaction_variance=float(v[ii,ii]),exposure_interaction_covariance=float(v[ei,ii]),iterations=result.fit_history.get('iteration'),converged=bool(result.converged)))
            except Exception as ex:per.append(dict(imputation=m,status='failed',error=repr(ex)))
            js(path,{**r,'fits':per})
        pd.DataFrame(per).to_csv(OUT/'per_imputation'/f"{j['task_id']}.csv",index=False)
        good=[v for v in per if v['status']=='ok']; r['n_imputations']=len(good)
        assert len(good)==30,'not all 30 imputations succeeded'
        q=pd.DataFrame(good); pooled=e.rubin_pool(q.interaction_beta,q.interaction_variance); r.update(pooled); r.update(e.effect_fields(r['beta'],r['beta_CI_lower'],r['beta_CI_upper']));r['fit_status']='completed'
    except Exception as ex:r.update(fit_status='failed',failure_reason=repr(ex));(OUT/'logs'/f"{j['task_id']}.log").write_text(traceback.format_exc())
    r.update(fits=per,elapsed_seconds=time.time()-started); js(path,r)
    (OUT/'logs'/f"{j['task_id']}__status.json").write_text(json.dumps({k:v for k,v in r.items() if k!='fits'},ensure_ascii=False,default=str,indent=2))
    print(j['task_id'],r['fit_status'],round(time.time()-started,1),flush=True);return r
def models():
    cfg=json.loads((OUT/'config.json').read_text()); jobs=cfg['jobs']
    checks=[]
    for cause in ['copd','chronic_lower_respiratory']:
        j=next(j for j in jobs if j['analysis_block']=='A' and j['outcome_id']==cause); r=fit(j)
        oldname='O10_temperature_adjusted_2009_2020' if cause=='copd' else 'D_'+cause
        src=OLD/'03_model_fits/checkpoints'/f'{oldname}.json'; old=json.loads(src.read_text())
        diff=abs(r.get('beta',np.inf)-old['beta']); vd=abs(r.get('total_variance',np.inf)-old['total_variance'])
        checks.append(dict(outcome_id=cause,beta_abs_diff=diff,variance_abs_diff=vd,same_sample=r['sample_hash']==old['sample_hash'],same_formula=r['formula']==old['formula'],same_draw=old['signature']['draw_file_sha256']==cfg['draw_sha256'],source=str(src),source_sha256=sha(src),passed=bool(diff<=1e-8 and vd<=1e-10 and r['sample_hash']==old['sample_hash'] and r['formula']==old['formula'] and old['signature']['draw_file_sha256']==cfg['draw_sha256'])))
    pd.DataFrame(checks).to_csv(OUT/'audit/entry_consistency.csv',index=False)
    assert all(x['passed'] for x in checks),'small-scale consistency failed; bulk models blocked'
    with ProcessPoolExecutor(max_workers=2) as pool:
        fs={pool.submit(fit,j):j for j in jobs}
        for f in as_completed(fs):
            try:f.result()
            except Exception as ex:
                j=fs[f];js(OUT/'checkpoints'/f"{j['task_id']}.json",{**j,'fit_status':'failed','failure_reason':repr(ex)})
def main():
    arg=argparse.ArgumentParser();arg.add_argument('stage',choices=['audit','models']);a=arg.parse_args()
    if a.stage=='audit':audit()
    else:models()
if __name__=='__main__':main()
