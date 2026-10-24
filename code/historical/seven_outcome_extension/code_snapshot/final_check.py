"""Delivery audit: protected original files, table/figure sources and task coverage."""
import run_extension as r
import pandas as pd
import numpy as np
import json,shutil,time
O=r.OUT
cfg=json.loads((O/'config.json').read_text());df=pd.read_csv(O/'AFIRE_7outcome_all_results.csv');checks=[]
def check(name,passed,details=''):checks.append(dict(check=name,passed=bool(passed),details=details))
check('all_results_unique',not df.duplicated(['outcome_id','analysis_block','model_id','contrast_id']).any())
for b,n in [('A',7),('B',35),('C',56),('D',35),('E',56)]:check('count_'+b,int(df.analysis_block.eq(b).sum())==n)
check('30_imputations_all_rows',df.n_imputations.eq(30).all())
check('all_model_contrasts_completed',df.fit_status.eq('completed').all())
for name,b in [('primary_7outcomes','A'),('marginal_associations_7outcomes','B'),('common_sample_7outcomes','C'),('targeted_omissions_7outcomes','D'),('LST_paired_7outcomes','E')]:
    part=pd.read_csv(O/(name+'.csv'));want=df[df.analysis_block.eq(b)].reset_index(drop=True)
    pd.testing.assert_frame_equal(part,want,check_dtype=False,atol=1e-12,rtol=1e-12);check('csv_matches_'+name,True)
for stem,b in [('primary_interaction','A'),('marginal_associations','B'),('common_environment','C'),('targeted_omissions','D'),('LST_pairs','E')]:
    part=pd.read_csv(O/'source_data'/f'{stem}.csv');pd.testing.assert_frame_equal(part,df[df.analysis_block.eq(b)].reset_index(drop=True),check_dtype=False,atol=1e-12,rtol=1e-12)
    check('figure_sources_'+stem,all((O/'figures'/f'{stem}.{ext}').is_file() for ext in ['png','svg','pdf']))
a=df[df.analysis_block.eq('A')].copy();order=np.argsort(a.P_value.to_numpy());expected=np.minimum(1,np.maximum.accumulate((7-np.arange(7))*a.P_value.to_numpy()[order]));check('Holm_independent_sorted_formula',np.allclose(a.P_adjusted.to_numpy()[order],expected,atol=1e-14,rtol=1e-12))
check('percent_transform',np.allclose(df.percent_estimate,100*np.expm1(df.beta),atol=1e-12,rtol=1e-12) and np.allclose(df.percent_CI_lower,100*np.expm1(df.beta_CI_lower),atol=1e-12,rtol=1e-12) and np.allclose(df.percent_CI_upper,100*np.expm1(df.beta_CI_upper),atol=1e-12,rtol=1e-12))
e,c,p,draws,z=r.load();exclusions=[];counts=[]
for j in cfg['jobs']:
    s=r.subset(j,c,p);key=pd.read_csv(O/'sample_keys'/f"{j['task_id']}.csv")
    check('actual_keys_'+j['task_id'],np.array_equal(s.row_id.to_numpy(),key.row_id.to_numpy()))
    per=pd.read_csv(O/'per_imputation'/f"{j['task_id']}.csv")
    det=per.exposure_variance*per.interaction_variance-per.exposure_interaction_covariance**2
    check('covariance_PSD_'+j['task_id'],bool((det>=-1e-14).all() and per.converged.all() and len(per)==30))
    base=p[p.cause_id.eq(j['outcome_id']) & p.year.between(2009,2020)]
    for _,row in base[~base.row_id.isin(s.row_id)].iterrows():
        why=[]
        if j['mode'] in ['drop2020','dropCA_and2020'] and row.year==2020:why.append('excluded year 2020')
        if j['mode'] in ['dropCA','dropCA_and2020'] and row.state_abbr=='CA':why.append('excluded California')
        if j['mode']=='dropCA2020only' and row.state_abbr=='CA' and row.year==2020:why.append('excluded California in 2020 only')
        req=r.requirements(c['formulas']['M3PL_joint'] if j['mode']=='common' else j['formula'])
        qa='relaxed' if j['mode']=='common' else j['mode']
        if qa in ['strict','relaxed'] and not row[qa+'_eligible']:why.append(qa+' daytime LST eligibility failed')
        for term in req:
            val=row[qa+'_lst'] if term=='day_LST_per10' and qa in ['strict','relaxed'] else row[term]
            if pd.isna(val):why.append('missing '+term)
        if row.population<=0 or pd.isna(row.population):why.append('nonpositive/missing population')
        exclusions.append(dict(task_id=j['task_id'],outcome_id=j['outcome_id'],county_fips=row.county_fips,state_abbr=row.state_abbr,year=row.year,row_id=row.row_id,reason='; '.join(why) or 'UNRESOLVED'))
    counts.append(dict(task_id=j['task_id'],outcome_id=j['outcome_id'],analysis_block=j['analysis_block'],model_id=j['model_id'],n_county_years=len(s),n_counties=s.county_fips.nunique(),n_states=s.state_abbr.nunique(),states=','.join(sorted(s.state_abbr.unique())),completely_excluded_states=','.join(sorted(set(base.state_abbr)-set(s.state_abbr))),completely_excluded_counties=','.join(map(str,sorted(set(base.county_fips)-set(s.county_fips)))),n_excluded_county_years=len(base)-len(s)))
pd.DataFrame(exclusions).to_csv(O/'audit/sample_exclusion_reasons.csv',index=False);pd.DataFrame(counts).to_csv(O/'audit/sample_counts_and_regions.csv',index=False)
check('all_exclusion_reasons_explained',all(v['reason']!='UNRESOLVED' for v in exclusions))
for cause in r.CAUSES:
    d=df[df.outcome_id.eq(cause)];ref=d[d.analysis_block.eq('A')].iloc[0];full=d[d.analysis_block.eq('D')&d.model_id.eq('full')].iloc[0]
    check('redundant_reference_agreement_'+cause,abs(ref.beta-full.beta)<1e-10 and ref.sample_hash==full.sample_hash)
before=pd.read_csv(O/'audit/original_files_before.csv');after=[]
for _,q in before.iterrows():
    path=r.Path(q.path);h=r.sha(path) if path.exists() else None
    after.append(dict(path=q.path,sha256_before=q.sha256,sha256_after=h,unchanged=h==q.sha256))
pd.DataFrame(after).to_csv(O/'audit/original_files_after.csv',index=False)
check('original_files_unchanged',all(a['unchanged'] for a in after),f'{len(after)} original files SHA256 checked; .venv and original __pycache__ excluded')
for file in ['independent_validation.csv','entry_consistency.csv','upstream_computational_checks.csv','raw_checks.csv']:
    q=pd.read_csv(O/'audit'/file);check(file,q.passed.all(),str(len(q)))
for path in O.glob('*.py'):shutil.copy2(path,O/'code_snapshot'/path.name)
required=['README.md','protocol_frozen.md','config.json','analysis_coverage_before.csv','analysis_coverage_after.csv','AFIRE_7outcome_all_results.csv','AFIRE_7outcome_results.xlsx','primary_7outcomes.csv','marginal_associations_7outcomes.csv','common_sample_7outcomes.csv','targeted_omissions_7outcomes.csv','LST_paired_7outcomes.csv','primary_multiplicity_7outcomes.csv','diagnostics_7outcomes.csv','RESULTS_SUMMARY_CN.md','AUDIT_REPORT.md']
check('required_deliverables',all((O/x).is_file() for x in required))
check('XLSX_verification_log',(O/'logs/xlsx_verification.log').exists() and 'cell-by-cell verified' in (O/'logs/xlsx_verification.log').read_text())
pd.DataFrame(checks).to_csv(O/'audit/delivery_checks.csv',index=False)
status='completed_and_validated' if all(a['passed'] for a in checks) else 'NOT_ACCEPTED'
checkpoint=[json.loads(path.read_text()) for path in (O/'checkpoints').glob('*.json')]
r.js(O/'audit/delivery_validation.json',dict(status=status,finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),n_checks=len(checks),n_passed=sum(a['passed'] for a in checks),model_tasks=154,model_imputation_fits=sum(len(a.get('fits',[])) for a in checkpoint),result_rows=len(df),sum_model_elapsed_seconds=sum(a.get('elapsed_seconds',0) for a in checkpoint),elapsed_note='sum across two workers is not wall time; freeze and final timestamps supplied',original_files_checked=len(after),original_files_unchanged=all(a['unchanged'] for a in after),output_root=str(O),all_results=str(O/'AFIRE_7outcome_all_results.csv')))
files=[p for p in O.rglob('*') if p.is_file() and 'cache' not in p.relative_to(O).parts and p.name!='output_manifest.csv']
pd.DataFrame([dict(path=str(p.relative_to(O)),size=p.stat().st_size,sha256=r.sha(p)) for p in sorted(files)]).to_csv(O/'audit/output_manifest.csv',index=False)
print(status,len(checks),'checks',sum(a['passed'] for a in checks),'passed')
assert status=='completed_and_validated'
