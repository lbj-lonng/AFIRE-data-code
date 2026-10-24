import run_extension as r
import numpy as np
import pandas as pd
import json,shutil
O=r.OUT;e,c,p,d,z=r.load();checks=[]
w=pd.read_csv(r.ROOT/c['inputs']['weight_model'])
state=p[['state_abbr','cause_id','year','state_deaths','state_population']].drop_duplicates().groupby(['state_abbr','cause_id']).agg(deaths=('state_deaths','sum'),population=('state_population','sum'))
rate=state.deaths/state.population
obs=p[p.deaths.notna()].groupby(['state_abbr','cause_id','county_fips']).agg(deaths=('deaths','sum'),population=('population','sum'))
med=p.groupby(['state_abbr','cause_id']).population.median()
for _,a in w.iterrows():
    key=(a.state_abbr,a.cause_id,int(a.county_fips));v=obs.loc[key] if key in obs.index else {'deaths':0,'population':0};sk=key[:2]
    prior=3*med.loc[sk];want=(v['deaths']+rate.loc[sk]*prior)/(v['population']+prior)
    checks.append(dict(check='EB_weight_rebuild',outcome_id=a.cause_id,county_fips=int(a.county_fips),error=abs(want-a.eb_history_rate),passed=bool(np.isclose(want,a.eb_history_rate,atol=1e-14,rtol=1e-10))))
ses=pd.read_csv(r.ROOT/'experiment_feasibility_20260906/source_snapshot/all/03/data_reference/county_year_ses.csv')
ses=ses[ses.state_abbr.isin(c['states']) & ses.period.eq('2006_2010')].drop_duplicates('county_fips').copy()
ses['expected']=(ses.ses_disadvantage_z-ses.ses_disadvantage_z.mean())/ses.ses_disadvantage_z.std(ddof=1)
a=p[['county_fips','ses_baseline_std']].drop_duplicates().merge(ses[['county_fips','expected']],on='county_fips',validate='one_to_one')
checks.append(dict(check='baseline_SES_source_scaling',error=float(abs(a.expected-a.ses_baseline_std).max()),passed=bool(np.allclose(a.expected,a.ses_baseline_std,rtol=0,atol=1e-12))))
source=r.ROOT/'paper_package_verified_20260908/data/analysis/COPD_fixed_EB_B1_1_9.npz';zz=np.load(source)
ix=pd.Series(np.arange(len(z['row_ids'])),index=z['row_ids']).loc[zz['row_ids']].to_numpy()
checks.append(dict(check='verified_package_COPD_draws_exact_match',source=str(source),sha256=r.sha(source),passed=bool(np.array_equal(zz['draws'],z['draws'][:,ix]))))
pd.DataFrame(checks).to_csv(O/'audit/upstream_computational_checks.csv',index=False)
snapshots=[r.ROOT/'experiment_longrun_20260906/scripts/gee_lst_extract.py',r.ROOT/'experiment_feasibility_20260906/source_snapshot/all/03/scripts/run_all.py',r.ROOT/'experiment_feasibility_20260906/source_snapshot/all/03/scripts/prepare_integrated_data_v6_3.py',r.ROOT/'experiment_closeout_v3/scripts/validate_qc_zero_source.py']
for path in snapshots:shutil.copy2(path,O/'code_snapshot'/path.name)
print('Upstream computational checks',sum(a['passed'] for a in checks),'/',len(checks))
assert all(a['passed'] for a in checks)
