from __future__ import annotations
import json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
ROOT=Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT',Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(ROOT/'scripts'))
from run_available_models_v6_3 import prepare
from run_one_model_v6_3 import SPECS
TABLES=ROOT/'tables'; LOGS=ROOT/'logs'

def main():
    data,draws=prepare(); rows=[]; status=[]
    for i,spec in enumerate(SPECS,1):
        name=spec['name']; print(f'[{i}/{len(SPECS)}] {name}',flush=True)
        subset=data.loc[data.year.between(spec['year_min'],spec['year_max'])].copy()
        if spec.get('filter_fn') is not None: subset=subset.loc[spec['filter_fn'](subset)].copy()
        needed=['population','row_id','county_fips','year']+spec['required']; subset=subset.dropna(subset=needed)
        try:
            Xdf=patsy.dmatrix(spec['rhs'],subset,return_type='dataframe'); X=np.asarray(Xdf,float); names=list(Xdf.columns)
            y=draws[:,subset.row_id.astype(int).to_numpy()].mean(axis=0); off=np.log(subset.population.to_numpy(float)); groups=subset.county_fips.to_numpy(int)
            p=sm.GLM(y,X,family=sm.families.Poisson(),offset=off).fit(maxiter=100)
            mu=np.asarray(p.fittedvalues); alpha=float(np.clip(np.sum((y-mu)**2-y)/max(np.sum(mu**2),1e-12),.001,2.0))
            f=sm.GLM(y,X,family=sm.families.NegativeBinomial(alpha=alpha),offset=off).fit(start_params=np.asarray(p.params),maxiter=100,cov_type='cluster',cov_kwds={'groups':groups})
            for term in spec['terms']:
                j=names.index(term); est=float(f.params[j]); se=float(f.bse[j]); lo=est-1.95996398454*se; hi=est+1.95996398454*se
                rows.append({'specification':name,'term':term,'estimate':est,'standard_error':se,'ci_low':lo,'ci_high':hi,'p_value':float(f.pvalues[j]),'irr':math.exp(est),'percent_change':(math.exp(est)-1)*100,'percent_change_ci_low':(math.exp(lo)-1)*100,'percent_change_ci_high':(math.exp(hi)-1)*100,'n_observations':len(subset),'n_counties':subset.county_fips.nunique(),'states_included':','.join(sorted(subset.state_abbr.unique())),'nb_alpha_fixed':alpha,'result_type':'30-draw mean outcome screening; use full MI for final inference'})
            status.append({'specification':name,'status':'completed','n_observations':len(subset),'n_counties':subset.county_fips.nunique()})
        except Exception as e:
            status.append({'specification':name,'status':'failed','reason':repr(e)})
            print('FAILED',e,flush=True)
    pd.DataFrame(rows).to_csv(TABLES/'screening_models_mean_mi_v6_3.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(status).to_csv(TABLES/'screening_model_status_v6_3.csv',index=False,encoding='utf-8-sig')
    (LOGS/'screening_status_v6_3.json').write_text(json.dumps({'completed':sum(x['status']=='completed' for x in status),'failed':sum(x['status']=='failed' for x in status)},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
