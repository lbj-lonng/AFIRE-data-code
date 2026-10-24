#!/usr/bin/env python3
"""COPD paired LST models on frozen county-year samples."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS","1"); os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
os.environ.setdefault("MKL_NUM_THREADS","1"); os.environ.setdefault("NUMEXPR_NUM_THREADS","1")
import numpy as np
import pandas as pd
import patsy

HERE=Path(__file__).resolve().parents[1]; ROOT=HERE.parent
FEAS=ROOT/"experiment_feasibility_20260906"; P4=FEAS/"source_snapshot/all/04"
os.environ["AFIRE_PROJECT_ROOT"]=str(P4); sys.path.insert(0,str(P4/"scripts"))
from v7_common import ModelSpec, load_analysis_data, filter_spec_data, rubin_pool
from v7_engine import build_design, estimate_nb_alpha, fit_negative_binomial

TERM="pm25_iqr:ses_baseline_std"
M2="pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)"
M3="pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + nonwildfire_pm25_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)"
M2REQ=("pm25_iqr","ses_baseline_std","age65_std_v7","density_std_v7","drought_d1_fs_std_v7","temperature_fs_std_v7")
M3REQ=M2REQ+("nonwildfire_pm25_std_v7","ozone_std_v7")
M2_NUISANCE="pm25_iqr + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)"

def spec(mid,rhs,req): return ModelSpec(model_id=mid,label=mid,group="lst_longrun",cause_id="copd",family="negative_binomial",rhs=rhs,
 exposure_term="pm25_iqr",interaction_term=TERM,required=tuple(req),year_min=2009,year_max=2020,min_rows=100,min_counties=10)
def key_hash(d):
 s="\n".join(f"{int(a):05d}-{int(b)}" for a,b in d[["county_fips","year"]].drop_duplicates().sort_values(["county_fips","year"]).itertuples(index=False,name=None))
 return hashlib.sha256(s.encode()).hexdigest()[:16]
def q_resid_ss(sub,add_lst):
 q=(sub.pm25_iqr*sub.ses_baseline_std).to_numpy(float); rhs=M2_NUISANCE+(" + day_LST_per10" if add_lst else "")
 Z=np.asarray(patsy.dmatrix(rhs,sub,return_type="dataframe"),float); coef=np.linalg.lstsq(Z,q,rcond=1e-10)[0]; r=q-Z@coef
 return float(r@r),int(np.linalg.matrix_rank(Z)),int(Z.shape[1])

def fit_job(mid,sub,rhs,req,draws,row_ids=None,checkdir=None):
 cp=checkdir/f"{mid}.json"
 if cp.exists():
  old=json.loads(cp.read_text())
  if old.get("status")=="completed": return old
 sp=spec(mid,rhs,req); _,X,names,idx=build_design(sub,sp)
 ids=sub.row_id.astype(int).to_numpy()
 if row_ids is None: outcomes=draws[:,ids]
 else:
  mapper=pd.Series(np.arange(len(row_ids)),index=row_ids); outcomes=draws[:,mapper.loc[ids].to_numpy(int)]
 offset=np.log(sub.population.to_numpy(float)); groups=sub.county_fips.to_numpy(int)
 alpha,warm=estimate_nb_alpha(outcomes.mean(axis=0),X,offset); fits=[]; started=time.time()
 for i,y in enumerate(outcomes,1):
  try:
   fit,_=fit_negative_binomial(y,X,offset,groups,alpha,warm); j=idx[TERM]
   fits.append({"imputation":i,"estimate":float(fit.params[j]),"variance":float(fit.cov_params()[j,j]),"status":"ok"})
  except Exception as e: fits.append({"imputation":i,"status":"failed","error":repr(e)})
  cp.write_text(json.dumps({"status":"running","fits":fits,"n_rows":len(sub),"sample_hash":key_hash(sub)},indent=2))
 good=[x for x in fits if x["status"]=="ok"]
 if not good: raise RuntimeError(mid+": all fits failed")
 pool=rubin_pool([x["estimate"] for x in good],[x["variance"] for x in good])
 out={**pool,"status":"completed" if len(good)==len(outcomes) else "partial","fits":fits,"n_rows":len(sub),
      "n_counties":int(sub.county_fips.nunique()),"sample_hash":key_hash(sub),"nb_alpha":float(alpha),
      "design_rank":int(np.linalg.matrix_rank(X)),"design_columns":int(X.shape[1]),"formula":rhs,
      "n_input":len(outcomes),"n_converged":len(good),"elapsed_seconds":time.time()-started}
 cp.write_text(json.dumps(out,indent=2)); return out

def row_from_fit(mid,label,model_family,sample_role,sub,r,imputation_version,lst_added):
 return {"model_id":mid,"label":label,"model_family":model_family,"sample_role":sample_role,"source":"new_fit",
  "beta":r["estimate"],"SE":r["standard_error"],"beta_CI_low":r["ci_low"],"beta_CI_high":r["ci_high"],
  "interaction_percent":100*np.expm1(r["estimate"]),"CI_percent_low":100*np.expm1(r["ci_low"]),"CI_percent_high":100*np.expm1(r["ci_high"]),
  "P_value":r["p_value"],"n_county_years":len(sub),"n_counties":sub.county_fips.nunique(),"sample_hash":key_hash(sub),
  "n_imputations":r["m_used"],"imputation_version":imputation_version,"between_variance":r["between_variance"],
  "monte_carlo_error":r["monte_carlo_error"],"nb_alpha":r["nb_alpha"],"design_rank":r["design_rank"],
  "design_columns":r["design_columns"],"convergence":f"{r['n_converged']}/{r['n_input']}","LST_added":lst_added,
  "formula":r["formula"],"offset":"log(population)","fixed_effects":"county + year","cluster_SE":"county"}

def reused_row(allm,model_id,label,family,role):
 z=allm[(allm.model_id==model_id)&(allm.term==TERM)].iloc[0]
 return {"model_id":model_id,"label":label,"model_family":family,"sample_role":role,"source":"reused_v7",
  "beta":z.estimate,"SE":z.standard_error,"beta_CI_low":z.ci_low,"beta_CI_high":z.ci_high,
  "interaction_percent":100*np.expm1(z.estimate),"CI_percent_low":100*np.expm1(z.ci_low),"CI_percent_high":100*np.expm1(z.ci_high),
  "P_value":z.p_value,"n_county_years":z.n_observations,"n_counties":z.n_counties,"sample_hash":"documented_existing_sample",
  "n_imputations":z.m_used,"imputation_version":"B0_0_9_history_EB_v5","between_variance":z.between_variance,
  "monte_carlo_error":z.monte_carlo_error,"nb_alpha":z.nb_alpha_fixed,"design_rank":z.design_rank,"design_columns":z.original_design_columns,
  "convergence":f"{int(z.successful_imputations)}/30","LST_added":False,"formula":z.rhs,"offset":"log(population)","fixed_effects":"county + year","cluster_SE":"county"}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--lst-panel",type=Path,required=True); ap.add_argument("--output-dir",type=Path,required=True); ap.add_argument("--resume",action="store_true")
 args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True); checkdir=args.output_dir/"checkpoints"; checkdir.mkdir(exist_ok=True)
 data,b0=load_analysis_data(); panel=pd.read_csv(args.lst_panel)
 lst=panel[(panel.period=="day")&(panel.QA_rule=="strict")].copy()
 lst["county_fips"]=lst.FIPS.astype(int); lst["day_LST_per10"]=lst.LST_C/10
 eligible=lst[lst.eligible_s070].copy(); mergecols=["county_fips","year","day_LST_per10","coverage"]
 allm=pd.read_csv(P4/"results/tables/all_pooled_models_v7.csv"); rows=[]
 rows.append(reused_row(allm,"O10_temperature_adjusted_2009_2020","A_M2_original_sample","M2","original_sample"))
 rows.append(reused_row(allm,"F03_nonwildfire_PM25_2009_2020","D_M3_original_sample","M3","original_sample"))
 samples={}
 for family,rhs,req in [("M2",M2,M2REQ),("M3",M3,M3REQ)]:
  base=filter_spec_data(data,spec("base_"+family,rhs,req)); sub=base.merge(eligible[mergecols],on=["county_fips","year"],how="inner",validate="one_to_one")
  samples[family]=sub
  for added in [False,True]:
   mid=f"{family}_{'with_dayLST' if added else 'noLST'}_eligible"
   rr=rhs+(" + day_LST_per10" if added else ""); rq=req+(("day_LST_per10",) if added else ())
   r=fit_job(mid,sub,rr,rq,b0,None,checkdir); rows.append(row_from_fit(mid,mid,family,"LST_eligible_common",sub,r,"B0_0_9_history_EB_v5",added))
 # Five predefined omission samples, paired without/with LST, M2 only. Full pair above is reused here by ID.
 full=samples["M2"]
 scenarios={"full":full,"exclude_2020":full[full.year!=2020].copy(),"exclude_CA":full[full.state_abbr!="CA"].copy(),
  "exclude_2020_and_CA":full[(full.year!=2020)&(full.state_abbr!="CA")].copy(),
  "exclude_CA_2020_only":full[~((full.year==2020)&(full.state_abbr=="CA"))].copy()}
 deletion=[]
 for scen,sub in scenarios.items():
  for added in [False,True]:
   mid=f"omit_{scen}_{'with_dayLST' if added else 'noLST'}"; rr=M2+(" + day_LST_per10" if added else ""); rq=M2REQ+(("day_LST_per10",) if added else ())
   if scen=="full": source=next(x for x in rows if x["model_id"]==f"M2_{'with_dayLST' if added else 'noLST'}_eligible")
   else:
    r=fit_job(mid,sub,rr,rq,b0,None,checkdir); source=row_from_fit(mid,mid,"M2",scen,sub,r,"B0_0_9_history_EB_v5",added)
   ss,rrank,rcols=q_resid_ss(sub,added)
   deletion.append({**source,"scenario":scen,"mean_LST_coverage":sub.coverage.mean(),"residualized_Q_SS":ss,
                    "Q_projection_rank":rrank,"Q_projection_columns":rcols})
 # Boundary B1 on the exact key model C sample.
 z=np.load(ROOT/"experiment_validation_stage3_20260906/copd_B1_1_9_draws.npz"); sub=full
 r=fit_job("M2_with_dayLST_eligible_B1_1_9",sub,M2+" + day_LST_per10",M2REQ+("day_LST_per10",),z["draws"],z["row_ids"],checkdir)
 boundary=[next(x for x in rows if x["model_id"]=="M2_with_dayLST_eligible"),
           row_from_fit("M2_with_dayLST_eligible_B1_1_9","B1_1_9","M2","LST_eligible_common",sub,r,"B1_1_9_history_EB_stage3",True)]
 pd.DataFrame(rows).to_csv(args.output_dir/"paired_LST_models.csv",index=False)
 deletion=pd.DataFrame(deletion)
 for added in [False,True]:
  den=deletion[(deletion.scenario=="full")&(deletion.LST_added==added)].residualized_Q_SS.iloc[0]
  deletion.loc[deletion.LST_added==added,"residualized_Q_SS_fraction_vs_full_same_design"]=deletion.loc[deletion.LST_added==added,"residualized_Q_SS"]/den
 deletion.to_csv(args.output_dir/"extreme_omission_paired_models.csv",index=False)
 pd.DataFrame(boundary).to_csv(args.output_dir/"LST_model_boundary_sensitivity.csv",index=False)
 # Strict nighttime is a separately screened supplemental branch. It is not
 # combined with daytime LST and does not alter the primary daytime models.
 night=panel[(panel.period=="night")&(panel.QA_rule=="strict")].copy()
 night["county_fips"]=night.FIPS.astype(int); night["night_LST_per10"]=night.LST_C/10
 night=night[night.eligible_s070].copy(); nmerge=["county_fips","year","night_LST_per10","coverage"]
 nrows=[]; nsamples={}
 for family,rhs,req,oldid in [("M2",M2,M2REQ,"O10_temperature_adjusted_2009_2020"),("M3",M3,M3REQ,"F03_nonwildfire_PM25_2009_2020")]:
  nrows.append(reused_row(allm,oldid,f"{family}_original_sample",family,"original_sample"))
  base=filter_spec_data(data,spec("night_base_"+family,rhs,req)); sub=base.merge(night[nmerge],on=["county_fips","year"],how="inner",validate="one_to_one")
  nsamples[family]=sub
  for added in [False,True]:
   mid=f"{family}_{'with_nightLST' if added else 'noLST'}_night_eligible"
   rr=rhs+(" + night_LST_per10" if added else ""); rq=req+(("night_LST_per10",) if added else ())
   r=fit_job(mid,sub,rr,rq,b0,None,checkdir); nrows.append(row_from_fit(mid,mid,family,"night_LST_eligible_common",sub,r,"B0_0_9_history_EB_v5",added))
 pd.DataFrame(nrows).to_csv(args.output_dir/"paired_night_LST_models.csv",index=False)
 # Predefined relaxed-QA sensitivity for day and night. Reuse the verified
 # original no-LST result when the branch retains exactly the original keys.
 qrows=[]
 for period,lstvar in [("day","day_LST_per10"),("night","night_LST_per10")]:
  q=panel[(panel.period==period)&(panel.QA_rule=="relaxed")].copy(); q["county_fips"]=q.FIPS.astype(int)
  q[lstvar]=q.LST_C/10; q=q[q.eligible_s070]
  for family,rhs,req,oldid in [("M2",M2,M2REQ,"O10_temperature_adjusted_2009_2020"),("M3",M3,M3REQ,"F03_nonwildfire_PM25_2009_2020")]:
   base=filter_spec_data(data,spec(f"relaxed_{period}_base_{family}",rhs,req))
   sub=base.merge(q[["county_fips","year",lstvar,"coverage"]],on=["county_fips","year"],how="inner",validate="one_to_one")
   if key_hash(sub)==key_hash(base):
    no=reused_row(allm,oldid,f"{family}_{period}_relaxed_noLST",family,f"{period}_relaxed_QA")
    no.update(sample_hash=key_hash(sub),n_county_years=len(sub),n_counties=sub.county_fips.nunique())
   else:
    mid=f"{family}_{period}_relaxed_noLST"; r=fit_job(mid,sub,rhs,req,b0,None,checkdir)
    no=row_from_fit(mid,mid,family,f"{period}_relaxed_QA",sub,r,"B0_0_9_history_EB_v5",False)
   qrows.append({**no,"period":period,"QA_rule":"relaxed"})
   mid=f"{family}_{period}_relaxed_withLST"; rr=rhs+f" + {lstvar}"; rq=req+(lstvar,)
   r=fit_job(mid,sub,rr,rq,b0,None,checkdir)
   yes=row_from_fit(mid,mid,family,f"{period}_relaxed_QA",sub,r,"B0_0_9_history_EB_v5",True)
   qrows.append({**yes,"period":period,"QA_rule":"relaxed"})
 pd.DataFrame(qrows).to_csv(args.output_dir/"paired_relaxed_QA_models.csv",index=False)
 keys=[]
 for family,sub in samples.items():
  for _,x in sub.iterrows(): keys.append({"period":"day","model_family":family,"county_fips":int(x.county_fips),"year":int(x.year),"sample_hash":key_hash(sub),"coverage":x.coverage})
 for family,sub in nsamples.items():
  for _,x in sub.iterrows(): keys.append({"period":"night","model_family":family,"county_fips":int(x.county_fips),"year":int(x.year),"sample_hash":key_hash(sub),"coverage":x.coverage})
 pd.DataFrame(keys).to_csv(args.output_dir/"model_common_sample_keys.csv",index=False)

if __name__=="__main__": main()
