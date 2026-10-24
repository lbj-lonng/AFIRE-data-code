from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np, pandas as pd, patsy, statsmodels.api as sm
ROOT=Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT',Path(__file__).resolve().parents[1])); sys.path.insert(0,str(ROOT/'scripts'))
from run_available_models_v6_3 import prepare
from run_one_model_v6_3 import SPECS
OUT=ROOT/'logs'/'screening_results_v6_3'; OUT.mkdir(parents=True,exist_ok=True)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--index',type=int,required=True); a=ap.parse_args(); spec=SPECS[a.index-1]; name=spec['name']; print(name,flush=True)
 data,draws=prepare(); sub=data.loc[data.year.between(spec['year_min'],spec['year_max'])].copy();
 if spec.get('filter_fn') is not None: sub=sub.loc[spec['filter_fn'](sub)].copy()
 sub=sub.dropna(subset=['population','row_id','county_fips','year']+spec['required'])
 try:
  Xdf=patsy.dmatrix(spec['rhs'],sub,return_type='dataframe'); X=np.asarray(Xdf,float); names=list(Xdf.columns); y=draws[:,sub.row_id.astype(int).to_numpy()].mean(axis=0); off=np.log(sub.population.to_numpy(float)); groups=sub.county_fips.to_numpy(int)
  p=sm.GLM(y,X,family=sm.families.Poisson(),offset=off).fit(maxiter=100); mu=np.asarray(p.fittedvalues); alpha=float(np.clip(np.sum((y-mu)**2-y)/max(np.sum(mu**2),1e-12),.001,2.0)); f=sm.GLM(y,X,family=sm.families.NegativeBinomial(alpha=alpha),offset=off).fit(start_params=np.asarray(p.params),maxiter=100,cov_type='cluster',cov_kwds={'groups':groups})
  rows=[]
  for term in spec['terms']:
   j=names.index(term); est=float(f.params[j]); se=float(f.bse[j]); lo=est-1.95996398454*se; hi=est+1.95996398454*se
   rows.append({'specification':name,'term':term,'estimate':est,'standard_error':se,'ci_low':lo,'ci_high':hi,'p_value':float(f.pvalues[j]),'irr':math.exp(est),'percent_change':(math.exp(est)-1)*100,'percent_change_ci_low':(math.exp(lo)-1)*100,'percent_change_ci_high':(math.exp(hi)-1)*100,'n_observations':len(sub),'n_counties':sub.county_fips.nunique(),'states_included':','.join(sorted(sub.state_abbr.unique())),'nb_alpha_fixed':alpha,'result_type':'30-draw mean-outcome screening; full MI required for final inference'})
  pd.DataFrame(rows).to_csv(OUT/f'{a.index:02d}_{name}.csv',index=False,encoding='utf-8-sig'); status={'specification':name,'status':'completed','n_observations':len(sub),'n_counties':sub.county_fips.nunique()};
  inter=[r for r in rows if ':' in r['term']][0]; print(f"interaction {inter['percent_change']:.3f}% p={inter['p_value']:.5g}",flush=True)
 except Exception as e:
  status={'specification':name,'status':'failed','reason':repr(e)}; print('FAILED',e,flush=True)
 (OUT/f'{a.index:02d}_{name}.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
