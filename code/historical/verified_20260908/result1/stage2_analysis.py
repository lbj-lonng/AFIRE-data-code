#!/usr/bin/env python3
"""Targeted stage-2 validation. Reads v6.3/v7 sources; writes only STAGE."""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np, pandas as pd, patsy

STAGE=Path(__file__).resolve().parent
ROOT=STAGE.parent
FEAS=ROOT/'experiment_feasibility_20260906'
P4=FEAS/'source_snapshot/all/04'
P3=FEAS/'source_snapshot/all/03'
os.environ['AFIRE_PROJECT_ROOT']=str(P4)
sys.path.insert(0,str(P4/'scripts'))
from v7_common import ModelSpec, load_analysis_data, filter_spec_data, rubin_pool
from v7_engine import build_design, estimate_nb_alpha, fit_negative_binomial

TERM='pm25_iqr:ses_baseline_std'
M2_RHS='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)'
M2_REQ=('pm25_iqr','ses_baseline_std','age65_std_v7','density_std_v7','drought_d1_fs_std_v7','temperature_fs_std_v7')
COMMON=('pm25_iqr','ses_baseline_std','age65_std_v7','density_std_v7','drought_d1_fs_std_v7','temperature_fs_std_v7','nonwildfire_pm25_std_v7','ozone_std_v7')
MODELS={
 'M0':('pm25_iqr + pm25_iqr:ses_baseline_std + C(county_model) + C(year_model)',('pm25_iqr','ses_baseline_std'),'none'),
 'M1':('pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + C(county_model) + C(year_model)',('pm25_iqr','ses_baseline_std','age65_std_v7','density_std_v7'),'age65;population_density'),
 'M2':(M2_RHS,M2_REQ,'age65;population_density;drought;air_temperature'),
 'M3':('pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + nonwildfire_pm25_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)',COMMON,'age65;population_density;drought;air_temperature;nonwildfire_PM25;ozone')}

def spec(model_id,rhs=M2_RHS,required=M2_REQ):
 return ModelSpec(model_id=model_id,label=model_id,group='stage2',cause_id='copd',family='negative_binomial',rhs=rhs,
  exposure_term='pm25_iqr',interaction_term=TERM,required=tuple(required),year_min=2009,year_max=2020,min_rows=100,min_counties=10)

def key_hash(d):
 s='\n'.join(f'{int(a):05d}-{int(b)}' for a,b in d[['county_fips','year']].drop_duplicates().sort_values(['county_fips','year']).itertuples(index=False,name=None))
 return hashlib.sha256(s.encode()).hexdigest()[:16]

def pool_to_row(pool):
 return dict(interaction_beta=pool['estimate'],pooled_SE=pool['standard_error'],interaction_percent=100*np.expm1(pool['estimate']),
  CI_lower=100*np.expm1(pool['ci_low']),CI_upper=100*np.expm1(pool['ci_high']),P_value=pool['p_value'])

def common_sample_table(data):
 old=pd.read_csv(FEAS/'new_model_pilot_fits.csv')
 meta=json.loads((P3/'logs/analysis_metadata_v5.json').read_text())
 base_ses=pd.read_csv(P3/'data_external/processed/county_ses_baseline_2006_2010_v6_3.csv')
 samples={}
 rows=[]
 for mid,(rhs,req,covs) in MODELS.items():
  sp=spec(mid,rhs,COMMON) # force exact shared keys, regardless of formula
  sub=filter_spec_data(data,sp); samples[mid]=set(map(tuple,sub[['county_fips','year']].to_numpy()))
  z=old[(old.model==mid)&(old['sample']=='common_sample')].iloc[0]
  rows.append(dict(model_id=mid,formula=rhs,covariates=covs,sample_id='common_'+key_hash(sub),year_range='2009-2020',
   n_counties=sub.county_fips.nunique(),n_county_years=len(sub),n_imputations=int(z.m_used),
   smoke_IQR_reference=f"{meta['pm25_iqr']:.15g} µg/m3; pooled unique county-years 2006-2020",
   SES_standardisation_reference=f"baseline 2006-2010; raw mean={base_ses.ses_disadvantage_z.mean():.15g}; raw SD={base_ses.ses_disadvantage_z.std(ddof=1):.15g}",
   interaction_beta=z.estimate,pooled_SE=z.standard_error,interaction_percent=100*np.expm1(z.estimate),
   CI_lower=100*np.expm1(z.ci_low),CI_upper=100*np.expm1(z.ci_high),P_value=z.p_value,
   convergence_status=f"{int(z.m_used)}/{int(z.m_used)} converged",sample_key_sha256_16=key_hash(sub),
   same_30_imputations=True,offset='log(population)',fixed_effects='county + year',cluster_SE='county',
   pooling_transform_order='Rubin pool beta/variance first; exponentiate pooled beta and CI second'))
 assert len({frozenset(v) for v in samples.values()})==1, 'M0-M3 county-year keys differ'
 out=pd.DataFrame(rows); out.to_csv(STAGE/'01_common_sample_models.csv',index=False)
 return out

def project_resid(y,Z,rcond=1e-10):
 coef,_,rank,s=np.linalg.lstsq(Z,y,rcond=rcond); resid=y-Z@coef
 tol=(s[0]*rcond if len(s) else np.nan)
 return resid,int(rank),float(tol),float(np.max(np.abs(Z.T@resid)))

def residual_diagnostics(data,draws):
 sub=filter_spec_data(data,spec('reference_M2'))
 sub=sub.sort_values(['county_fips','year']).copy()
 X=sub.pm25_iqr.to_numpy(float); S=sub.ses_baseline_std.to_numpy(float); Q=X*S
 sub['X_county_centered']=X-sub.groupby('county_fips').pm25_iqr.transform('mean').to_numpy(float)
 sub['Q']=Q; sub['Q_county_centered']=Q-sub.groupby('county_fips').Q.transform('mean').to_numpy(float)
 fe=np.asarray(patsy.dmatrix('0 + C(county_model) + C(year_model)',sub,return_type='dataframe'),float)
 sub['X_FE_resid'],rank_fe,tol_fe,orth_x=project_resid(X,fe)
 sub['Q_FE_resid'],_,_,orth_q=project_resid(Q,fe)
 nuisance=np.asarray(patsy.dmatrix('pm25_iqr + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)',sub,return_type='dataframe'),float)
 sub['Q_full_resid'],rank_full,tol_full,orth_full=project_resid(Q,nuisance)
 ids=sub.row_id.astype(int).to_numpy(); sub['death_mi_mean']=draws[:,ids].mean(axis=0)
 sub['group']=np.select([
  sub.state_abbr.eq('CA')&sub.year.eq(2020),sub.state_abbr.eq('CA')&sub.year.ne(2020),
  sub.state_abbr.ne('CA')&sub.year.eq(2020)],['California × 2020','California × other years','Other five states × 2020'],default='Other five states × other years')
 metrics={'smoke_design_ss':'X_county_centered','interaction_county_centered_ss':'Q_county_centered',
          'smoke_FE_residual_ss':'X_FE_resid','interaction_FE_residual_ss':'Q_FE_resid','residualized_interaction_ss':'Q_full_resid'}
 totals={k:float((sub[v]**2).sum()) for k,v in metrics.items()}
 rows=[]
 order=['California × 2020','California × other years','Other five states × 2020','Other five states × other years']
 for group in order:
  g=sub[sub.group==group]; r=dict(group=group,n_observations=len(g),n_counties=g.county_fips.nunique(),
    population_sum=g.population.sum(),death_events_MI_mean=g.death_mi_mean.sum(),sample_id='reference_M2_'+key_hash(sub),
    years='2009-2020',smoke_scale='fixed IQR units',SES_scale='fixed baseline SD units',population_weighted=False,
    centering='residuals generated once in full reference sample; then partitioned',projection_method='numpy.linalg.lstsq',rcond=1e-10,
    FE_projection_rank=rank_fe,FE_projection_columns=fe.shape[1],full_projection_rank=rank_full,full_projection_columns=nuisance.shape[1],
    numerical_tolerance=max(tol_fe,tol_full),max_normal_equation_residual=max(orth_x,orth_q,orth_full))
  for k,v in metrics.items():
   val=float((g[v]**2).sum()); r[k]=val; r[k+'_share']=val/totals[k]
  rows.append(r)
 out=pd.DataFrame(rows)
 for c in [x for x in out if x.endswith('_share')]:
  assert abs(out[c].sum()-1)<1e-10, (c,out[c].sum())
 out.to_csv(STAGE/'02_joint_extreme_design_diagnostics.csv',index=False)
 return out,sub

def fit_subset(job_id,sub,draws,checkpoint_file,method_label):
 checkpoint={}
 if checkpoint_file.exists(): checkpoint=json.loads(checkpoint_file.read_text())
 if job_id in checkpoint and checkpoint[job_id].get('status')=='completed': return checkpoint[job_id]
 sp=spec(job_id); _,X,names,idx=build_design(sub,sp); ids=sub.row_id.astype(int).to_numpy()
 outcomes=draws if draws.shape[1]==len(sub) else draws[:,ids]
 offset=np.log(sub.population.to_numpy(float)); groups=sub.county_fips.to_numpy(int)
 alpha,warm=estimate_nb_alpha(outcomes.mean(axis=0),X,offset); est=[]; var=[]; failed=[]; started=time.time()
 for i,y in enumerate(outcomes,1):
  try:
   fit,_=fit_negative_binomial(y,X,offset,groups,alpha,warm); j=idx[TERM]
   est.append(float(fit.params[j])); var.append(float(fit.cov_params()[j,j]))
  except Exception as e: failed.append({'imputation':i,'error':repr(e)})
  print(f'{job_id}: {i}/{len(outcomes)}',flush=True)
 if not est: raise RuntimeError(f'{job_id}: all fits failed')
 po=rubin_pool(est,var); result={**po,'job_id':job_id,'method':method_label,'status':'completed' if not failed else 'partial',
  'n_county_years':len(sub),'n_counties':sub.county_fips.nunique(),'sample_hash':key_hash(sub),'n_imputations_input':len(outcomes),
  'n_imputations_converged':len(est),'failures':failed,'nb_alpha':alpha,'design_rank':int(np.linalg.matrix_rank(X)),
  'design_columns':X.shape[1],'elapsed_seconds':time.time()-started}
 checkpoint[job_id]=result; checkpoint_file.write_text(json.dumps(checkpoint,ensure_ascii=False,indent=2))
 return result

def q_resid_ss(sub):
 q=(sub.pm25_iqr*sub.ses_baseline_std).to_numpy(float)
 z=np.asarray(patsy.dmatrix('pm25_iqr + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)',sub,return_type='dataframe'),float)
 r,rank,tol,orth=project_resid(q,z); return float(r@r),rank,z.shape[1]

def omission_models(data,draws):
 full=filter_spec_data(data,spec('reference_M2'))
 cp=STAGE/'omission_model_checkpoint.json'
 new={}
 samples={'D_exclude_2020_and_CA':full[(full.year!=2020)&(full.state_abbr!='CA')].copy(),
          'E_exclude_CA_2020_only':full[~((full.year==2020)&(full.state_abbr=='CA'))].copy()}
 for job,sub in samples.items(): new[job]=fit_subset(job,sub,draws,cp,'eb_history')
 allm=pd.read_csv(P4/'results/tables/all_pooled_models_v7.csv')
 ids={'A_full':'O10_temperature_adjusted_2009_2020','B_exclude_2020':'Y2020_leave_out','C_exclude_CA':'LCA_leave_out'}
 rows=[]
 for label,mid in ids.items():
  z=allm[(allm.model_id==mid)&(allm.term==TERM)].iloc[0]
  if label=='A_full': sub=full
  elif label=='B_exclude_2020': sub=full[full.year!=2020]
  else: sub=full[full.state_abbr!='CA']
  ss,rank,ncol=q_resid_ss(sub)
  rows.append(dict(scenario=label,source='reused v7 exact reference-model result',model_id=mid,beta_interaction=z.estimate,pooled_SE=z.standard_error,
   beta_CI_low=z.ci_low,beta_CI_high=z.ci_high,interaction_percent=100*np.expm1(z.estimate),CI_lower=100*np.expm1(z.ci_low),CI_upper=100*np.expm1(z.ci_high),
   n_county_years=len(sub),n_counties=sub.county_fips.nunique(),n_imputations=z.m_used,convergence=f'{int(z.m_used)}/{int(z.m_used)}',
   sample_hash=key_hash(sub),residualized_Q_SS=ss,design_rank=rank,design_columns=ncol))
 for label,r in new.items():
  sub=samples[label]; ss,rank,ncol=q_resid_ss(sub)
  rows.append(dict(scenario=label,source='new targeted 30-imputation refit',model_id=r['job_id'],beta_interaction=r['estimate'],pooled_SE=r['standard_error'],
   beta_CI_low=r['ci_low'],beta_CI_high=r['ci_high'],interaction_percent=100*np.expm1(r['estimate']),CI_lower=100*np.expm1(r['ci_low']),CI_upper=100*np.expm1(r['ci_high']),
   n_county_years=len(sub),n_counties=sub.county_fips.nunique(),n_imputations=r['m_used'],convergence=f"{r['n_imputations_converged']}/{r['n_imputations_input']}",
   sample_hash=key_hash(sub),residualized_Q_SS=ss,design_rank=rank,design_columns=ncol))
 out=pd.DataFrame(rows); ref=out[out.scenario=='A_full'].iloc[0]
 out['absolute_beta_change_vs_full']=out.beta_interaction-ref.beta_interaction
 out['relative_beta_change_vs_full']=np.where(abs(ref.beta_interaction)>=1e-6,(out.beta_interaction-ref.beta_interaction)/abs(ref.beta_interaction),np.nan)
 out['relative_change_interpretable']=abs(ref.beta_interaction)>=1e-6; out['SE_ratio_vs_full']=out.pooled_SE/ref.pooled_SE
 out['residualized_Q_SS_fraction_vs_full']=out.residualized_Q_SS/ref.residualized_Q_SS
 out['formula']=M2_RHS; out['smoke_and_SES_scale']='fixed project-wide pm25 IQR and baseline SES SD; not recomputed after deletion'
 out['offset']='log(population)'; out['fixed_effects']='county + year'; out['cluster_SE']='county'; out['same_imputation_file']=True
 out.to_csv(STAGE/'03_targeted_omission_models.csv',index=False); return out

def fit_imputation_method(job_id,sub,outcomes,cp,label):
 return fit_subset(job_id,sub,outcomes,cp,label)

def imputation_sensitivity(data,main_draws):
 full=filter_spec_data(data,spec('reference_M2')); cp=STAGE/'imputation_model_checkpoint.json'; rows=[]
 allm=pd.read_csv(P4/'results/tables/all_pooled_models_v7.csv')
 z=allm[(allm.model_id=='O10_temperature_adjusted_2009_2020')&(allm.term==TERM)].iloc[0]
 rows.append(dict(method='history_burden_EB',source='reused v7',interaction_beta=z.estimate,pooled_SE=z.standard_error,
  CI_low=z.ci_low,CI_high=z.ci_high,n_county_years=len(full),n_counties=full.county_fips.nunique(),m=z.m_used,
  within_variance=z.within_variance,between_variance=z.between_variance,fraction_missing_information=z.fraction_missing_information,
  monte_carlo_error=z.monte_carlo_error,convergence=f'{int(z.m_used)}/{int(z.m_used)}',sample_hash=key_hash(full)))
 for method,file in [('population_weight','imputed_deaths_population_only_v5.npz'),('equal_weight','imputed_deaths_equal_weight_v5.npz')]:
  arr=np.load(P3/'data_processed'/file)['draws']; r=fit_imputation_method('imp_'+method,full,arr,cp,method)
  rows.append(dict(method=method,source='new fixed-M2 fit using existing draws',interaction_beta=r['estimate'],pooled_SE=r['standard_error'],
   CI_low=r['ci_low'],CI_high=r['ci_high'],n_county_years=len(full),n_counties=full.county_fips.nunique(),m=r['m_used'],
   within_variance=r['within_variance'],between_variance=r['between_variance'],fraction_missing_information=r['fraction_missing_information'],
   monte_carlo_error=r['monte_carlo_error'],convergence=f"{r['n_imputations_converged']}/{r['n_imputations_input']}",sample_hash=key_hash(full)))
 # Complete-case uses one observed outcome vector and the same covariate/model definition.
 cc=full[full.deaths.notna()].copy(); r=fit_imputation_method('imp_complete_case',cc,cc.deaths.to_numpy(float)[None,:],cp,'complete_case')
 rows.append(dict(method='complete_case',source='new fixed-M2 fit; observed death counts only',interaction_beta=r['estimate'],pooled_SE=r['standard_error'],
  CI_low=r['ci_low'],CI_high=r['ci_high'],n_county_years=len(cc),n_counties=cc.county_fips.nunique(),m=1,
  within_variance=r['within_variance'],between_variance=np.nan,fraction_missing_information=np.nan,monte_carlo_error=np.nan,
  convergence=f"{r['n_imputations_converged']}/1",sample_hash=key_hash(cc)))
 out=pd.DataFrame(rows); out['interaction_percent']=100*np.expm1(out.interaction_beta)
 out['CI_percent_low']=100*np.expm1(out.CI_low); out['CI_percent_high']=100*np.expm1(out.CI_high)
 out['records_retained_fraction_vs_MI']=out.n_county_years/len(full)
 out['suppression_semantic_status']='PENDING/FAILED: archived algorithms allow 0 for Suppressed although public zeros are separate; query provenance not archived'
 out['formula']=M2_RHS; out['offset']='log(population)'; out['fixed_effects']='county + year'; out['cluster_SE']='county'
 out.to_csv(STAGE/'04_fixed_model_imputation_sensitivity.csv',index=False)
 return out

def semantic_check(data):
 p=pd.read_csv(P3/'data_processed/county_year_disease_panel_base_v5.csv',low_memory=False)
 g=p.groupby(['state_abbr','year','cause_id']).agg(state_deaths=('state_deaths','first'),observed=('deaths','sum'),n_suppressed=('death_suppressed','sum'))
 g['gap']=g.state_deaths-g.observed; g['feasible_1_9']=(g.gap>=g.n_suppressed)&(g.gap<=9*g.n_suppressed)
 rows=[
  ('public_zero_death_rows',int(pd.to_numeric(p.deaths_raw,errors='coerce').eq(0).sum()),'distinct from Suppressed'),
  ('explicit_Suppressed_rows',int(p.death_suppressed.sum()),'parsed only when deaths_raw exactly Suppressed'),
  ('visible_count_unreliable_rate_rows',int((p.deaths.notna()&p.rate_unreliable).sum()),'count retained; unreliable applies to rate'),
  ('missing_or_unparsed_nonSuppressed_death_rows',int((p.deaths.isna()&~p.death_suppressed).sum()),'zero in archived panel'),
  ('missing_expected_county_year_outcome_keys',int(p.county_fips.nunique()*p.year.nunique()*p.cause_id.nunique()-len(p)),'zero in archived six-state Cartesian grid'),
  ('state_year_outcome_groups_not_feasible_under_1_9',int((~g.feasible_1_9).sum()),'all 630 are feasible under 1-9'),
 ]
 for method in ['eb_history','population_only','equal_weight']:
  a=np.load(P3/f'data_processed/imputed_deaths_{method}_v5.npz')['draws'][:,p.death_suppressed.to_numpy(bool)]
  rows.append((method+'_imputed_zero_values_for_Suppressed',int((a==0).sum()),'semantic conflict requiring source-rule resolution'))
 out=pd.DataFrame(rows,columns=['check','value','interpretation']); out.to_csv(STAGE/'suppression_semantic_check.csv',index=False)
 return out

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--prepare-only',action='store_true'); args=ap.parse_args()
 data,draws=load_analysis_data(); semantic_check(data); common_sample_table(data); joint,_=residual_diagnostics(data,draws)
 if args.prepare_only: return
 omission=omission_models(data,draws); imp=imputation_sensitivity(data,draws)
 print(json.dumps({'common_models':4,'joint_groups':len(joint),'omission_models':len(omission),'imputation_methods':len(imp)},indent=2))

if __name__=='__main__': main()
