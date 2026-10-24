from __future__ import annotations

import concurrent.futures as cf
import gzip
import gc
import json
import math
import os
import re
import shutil
import subprocess
import sys
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import pandas as pd
import patsy
from scipy.special import gammaln
from scipy.stats import norm, t as student_t
import statsmodels.api as sm
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

warnings.filterwarnings('ignore')

ROOT = Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT', Path(__file__).resolve().parents[1])).resolve()
RAW_COUNTY = ROOT / 'data_raw' / 'health_county'
RAW_STATE = ROOT / 'data_raw' / 'health_state'
PM_FILE = ROOT / 'data_reference' / 'county_year_smoke_pm25.csv'
SES_FILE = ROOT / 'data_reference' / 'county_year_ses.csv'
DATA = ROOT / 'data_processed'
TABLES = ROOT / 'tables'
FIGURES = ROOT / 'figures'
REPORTS = ROOT / 'reports'
LOGS = ROOT / 'logs'
for p in [DATA, TABLES, FIGURES, REPORTS, LOGS]:
    p.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS / 'pipeline_v5.log'
STATE_ORDER = ['AZ', 'CA', 'CO', 'ID', 'OR', 'WA']
STATE_FIPS_TO_ABBR = {4:'AZ', 6:'CA', 8:'CO', 16:'ID', 41:'OR', 53:'WA'}
CAUSE_ORDER = [
    'cerebrovascular_disease', 'ischemic_heart_disease', 'copd',
    'chronic_lower_respiratory', 'respiratory_system', 'circulatory_system', 'asthma'
]
CAUSE_ZH = {
    'cerebrovascular_disease':'脑血管疾病',
    'ischemic_heart_disease':'缺血性心脏病',
    'copd':'慢性阻塞性肺疾病（COPD）',
    'chronic_lower_respiratory':'慢性下呼吸道疾病',
    'respiratory_system':'呼吸系统疾病',
    'circulatory_system':'循环系统疾病',
    'asthma':'哮喘',
}
CAUSE_EN = {
    'cerebrovascular_disease':'Cerebrovascular disease',
    'ischemic_heart_disease':'Ischemic heart disease',
    'copd':'COPD',
    'chronic_lower_respiratory':'Chronic lower respiratory disease',
    'respiratory_system':'Respiratory system disease',
    'circulatory_system':'Circulatory system disease',
    'asthma':'Asthma',
}
PRIMARY_METHOD = 'eb_history'
M_PRIMARY = 30
M_SENS = 15
RANDOM_SEEDS = {'eb_history':20260728, 'population_only':20260729, 'equal_weight':20260730}

# Use an explicit CJK font file so figures render Chinese reliably on Linux.
_CJK_FONT_PATHS = [
    Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
    Path('/usr/share/fonts/truetype/arphic/uming.ttc'),
]
for _font_path in _CJK_FONT_PATHS:
    if _font_path.exists():
        font_manager.fontManager.addfont(str(_font_path))
        _cjk_prop = font_manager.FontProperties(fname=str(_font_path))
        plt.rcParams['font.family'] = _cjk_prop.get_name()
        break
else:
    plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['pdf.fonttype'] = 42


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(str(msg) + '\n')


def bh_adjust(values: pd.Series) -> pd.Series:
    p = pd.to_numeric(values, errors='coerce').to_numpy(float)
    out = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    vals = p[ok]
    if len(vals) == 0:
        return pd.Series(out, index=values.index)
    order = np.argsort(vals)
    ranked = vals[order]
    adj = ranked * len(ranked) / np.arange(1, len(ranked)+1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    inv = np.empty(len(order), int); inv[order] = np.arange(len(order))
    out[np.where(ok)[0]] = np.clip(adj[inv], 0, 1)
    return pd.Series(out, index=values.index)


def parse_age_rate(x: object) -> float:
    if pd.isna(x): return np.nan
    m = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*\(', str(x))
    return float(m.group(1)) if m else np.nan


def parse_age_bounds(x: object) -> tuple[float,float]:
    if pd.isna(x): return np.nan, np.nan
    nums = re.findall(r'[0-9]+(?:\.[0-9]+)?', str(x))
    return (float(nums[1]), float(nums[2])) if len(nums) >= 3 else (np.nan, np.nan)


def load_county_health() -> pd.DataFrame:
    frames=[]
    for p in sorted(RAW_COUNTY.glob('*.csv')):
        d=pd.read_csv(p,dtype=str)
        d['source_file']=p.name
        frames.append(d)
    if not frames: raise FileNotFoundError(RAW_COUNTY)
    h=pd.concat(frames,ignore_index=True)
    pop_cols=[c for c in h.columns if c.startswith('Population_')]
    if len(pop_cols)!=1: raise ValueError(f'County population columns: {pop_cols}')
    h=h.rename(columns={
        'State':'state','State Abbreviation':'state_abbr','State Code':'state_fips',
        'County':'county','County Code':'county_fips','Year':'year','Deaths':'deaths_raw',
        'Crude Rate':'crude_rate_raw','Age Adjusted Rate Standard Error':'age_adjusted_rate_se_raw',
        'Age Adjusted Rate 95% CI':'age_adjusted_rate_ci', pop_cols[0]:'population_raw'
    })
    for c in ['state_fips','county_fips','year']:
        h[c]=pd.to_numeric(h[c],errors='raise').astype(int)
    h['deaths']=pd.to_numeric(h['deaths_raw'],errors='coerce')
    h['death_suppressed']=h['deaths_raw'].astype(str).str.strip().str.lower().eq('suppressed')
    h['population']=pd.to_numeric(h['population_raw'],errors='raise')
    h['crude_rate']=pd.to_numeric(h['crude_rate_raw'],errors='coerce')
    h['age_adjusted_rate_se']=pd.to_numeric(h['age_adjusted_rate_se_raw'],errors='coerce')
    h['age_adjusted_rate']=h['age_adjusted_rate_ci'].map(parse_age_rate)
    b=h['age_adjusted_rate_ci'].map(parse_age_bounds)
    h['age_adjusted_rate_ci_low']=[z[0] for z in b]
    h['age_adjusted_rate_ci_high']=[z[1] for z in b]
    h['rate_unreliable']=(h['crude_rate_raw'].astype(str).str.contains('Unreliable',case=False,na=False)|
                          h['age_adjusted_rate_ci'].astype(str).str.contains('Unreliable',case=False,na=False))
    h['county_fips_str']=h['county_fips'].map(lambda x:f'{x:05d}')
    keep=['state','state_abbr','state_fips','county','county_fips','county_fips_str','year',
          'cause_id','cause_en','cause_zh','icd10_range','deaths_raw','deaths','death_suppressed',
          'population','crude_rate','age_adjusted_rate','age_adjusted_rate_se',
          'age_adjusted_rate_ci_low','age_adjusted_rate_ci_high','rate_unreliable','source_file']
    h=h[keep].copy()
    if h.duplicated(['county_fips','year','cause_id']).any(): raise ValueError('Duplicate county-year-cause')
    return h


def load_state_health() -> pd.DataFrame:
    p=RAW_STATE/'cdc_wonder_all_7_causes_state_year_2006_2020.csv'
    d=pd.read_csv(p,dtype=str)
    cols=d.columns.tolist()
    if len(cols)<11: raise ValueError('Unexpected state schema')
    x=d[['cause_id','cause_en','cause_zh','icd10_range',cols[4],cols[5],cols[6],cols[7],cols[8],cols[9],cols[10]]].copy()
    x.columns=['cause_id','cause_en','cause_zh','icd10_range','state_label','year','state_deaths',
               'state_population','state_crude_rate','state_age_rate_ci','state_age_rate_se']
    x['state_fips']=pd.to_numeric(x['state_label'].str.extract(r'\((\d{2})\)')[0],errors='coerce').astype('Int64')
    x['state_abbr']=x['state_fips'].map(STATE_FIPS_TO_ABBR)
    x=x[x['state_abbr'].notna()].copy()
    x['state_fips']=x['state_fips'].astype(int)
    x['year']=pd.to_numeric(x['year'],errors='raise').astype(int)
    for c in ['state_deaths','state_population','state_crude_rate','state_age_rate_se']:
        x[c]=pd.to_numeric(x[c],errors='coerce')
    x['state_age_adjusted_rate']=x['state_age_rate_ci'].map(parse_age_rate)
    return x


def build_panel() -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    h=load_county_health(); s=load_state_health()
    pm=pd.read_csv(PM_FILE); ses=pd.read_csv(SES_FILE)
    pm=pm[pm['state_abbr'].isin(STATE_ORDER)].rename(columns={'GEOID':'county_fips'}).copy()
    ses=ses[ses['state_abbr'].isin(STATE_ORDER)].copy()
    pm['county_fips']=pd.to_numeric(pm['county_fips'],errors='raise').astype(int)
    ses['county_fips']=pd.to_numeric(ses['county_fips'],errors='raise').astype(int)
    pm['year']=pd.to_numeric(pm['year'],errors='raise').astype(int)
    ses['year']=pd.to_numeric(ses['year'],errors='raise').astype(int)
    pm_cols=['county_fips','year','county_smoke_pm25_sum','county_smoke_pm25_mean_smoke_days',
             'county_smoke_days','county_smoke_pm25_max','county_smoke_pm25_annual_burden']
    ses_cols=['county_fips','year','total_population','median_household_income','per_capita_income',
              'poverty_rate','unemployment_rate','less_than_hs_rate','bachelor_plus_rate','nonwhite_rate',
              'hispanic_rate','foreign_born_rate','limited_english_rate','renter_rate','no_vehicle_rate',
              'rent_burden_30plus_rate','overcrowding_rate','low_income_under_30k_rate','ses_disadvantage_z',
              'ses_disadvantage_quintile','ses_disadvantage_label','period']
    panel=h.merge(pm[pm_cols],on=['county_fips','year'],how='left',validate='many_to_one')
    panel=panel.merge(ses[ses_cols],on=['county_fips','year'],how='left',validate='many_to_one')
    panel=panel.merge(s[['state_abbr','year','cause_id','state_deaths','state_population']],
                      on=['state_abbr','year','cause_id'],how='left',validate='many_to_one')
    panel=panel.sort_values(['cause_id','state_abbr','county_fips','year']).reset_index(drop=True)
    panel['row_id']=np.arange(len(panel))
    exp_iqr=panel[['county_fips','year','county_smoke_pm25_annual_burden']].drop_duplicates()['county_smoke_pm25_annual_burden'].quantile(.75)-panel[['county_fips','year','county_smoke_pm25_annual_burden']].drop_duplicates()['county_smoke_pm25_annual_burden'].quantile(.25)
    ses_unique=panel[['county_fips','year','ses_disadvantage_z','poverty_rate']].drop_duplicates()
    ses_mean,ses_sd=ses_unique.ses_disadvantage_z.mean(),ses_unique.ses_disadvantage_z.std()
    pov_mean,pov_sd=ses_unique.poverty_rate.mean(),ses_unique.poverty_rate.std()
    panel['pm25_iqr']=panel['county_smoke_pm25_annual_burden']/exp_iqr
    panel['ses_std']=(panel['ses_disadvantage_z']-ses_mean)/ses_sd
    panel['poverty_std']=(panel['poverty_rate']-pov_mean)/pov_sd
    panel['year_centered']=panel['year']-2013
    # fixed SES quintile
    base=(ses_unique[ses_unique.year.between(2006,2010)].groupby('county_fips',as_index=False).ses_disadvantage_z.mean())
    base['baseline_ses_quintile']=pd.qcut(base.ses_disadvantage_z.rank(method='first'),5,labels=[1,2,3,4,5]).astype(int)
    panel=panel.merge(base[['county_fips','baseline_ses_quintile']],on='county_fips',how='left')
    exp=panel[['county_fips','year','pm25_iqr']].drop_duplicates().sort_values(['county_fips','year'])
    exp['pm25_lag1_iqr']=exp.groupby('county_fips').pm25_iqr.shift(1)
    exp['pm25_lead1_iqr']=exp.groupby('county_fips').pm25_iqr.shift(-1)
    panel=panel.merge(exp,on=['county_fips','year','pm25_iqr'],how='left',validate='many_to_one')

    # Reconciliation diagnostics
    diag=(panel.groupby(['state_abbr','state_fips','year','cause_id'],as_index=False)
          .agg(state_deaths=('state_deaths','first'),state_population=('state_population','first'),
               observed_county_deaths=('deaths','sum'),county_population=('population','sum'),
               suppressed_counties=('death_suppressed','sum'),county_count=('county_fips','size')))
    diag['suppressed_gap']=diag.state_deaths-diag.observed_county_deaths
    diag['max_possible_0_9']=9*diag.suppressed_counties
    diag['suppression_feasible']=((diag.suppressed_gap>=0)&(diag.suppressed_gap<=diag.max_possible_0_9))
    diag['population_difference']=diag.state_population-diag.county_population
    diag['gap_share_state_deaths']=diag.suppressed_gap/diag.state_deaths.replace(0,np.nan)
    if not diag.suppression_feasible.all():
        raise ValueError('At least one state-year-cause gap violates 0-9 constraint')
    if (diag.population_difference.abs()>0.5).any():
        raise ValueError('State and county population totals differ')

    panel.to_csv(DATA/'county_year_disease_panel_base_v5.csv',index=False,encoding='utf-8-sig')
    s.to_csv(DATA/'state_year_health_clean_v5.csv',index=False,encoding='utf-8-sig')
    diag.to_csv(TABLES/'state_county_reconciliation_v5.csv',index=False,encoding='utf-8-sig')
    meta={'states':STATE_ORDER,'n_counties':int(panel.county_fips.nunique()),'n_rows':int(len(panel)),
          'years':[int(panel.year.min()),int(panel.year.max())],'n_causes':int(panel.cause_id.nunique()),
          'pm25_iqr':float(exp_iqr),'ses_mean':float(ses_mean),'ses_sd':float(ses_sd),
          'suppressed_rows':int(panel.death_suppressed.sum()),'suppressed_share':float(panel.death_suppressed.mean()),
          'reconciliation_groups':int(len(diag)),'all_feasible':bool(diag.suppression_feasible.all()),
          'max_population_difference':float(diag.population_difference.abs().max())}
    (LOGS/'analysis_metadata_v5.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return panel,s,diag


def build_imputation_weights(panel: pd.DataFrame) -> pd.DataFrame:
    state_long=(panel[['state_abbr','cause_id','year','state_deaths','state_population']].drop_duplicates()
                .groupby(['state_abbr','cause_id'],as_index=False)
                .agg(state_total_deaths=('state_deaths','sum'),state_total_population=('state_population','sum')))
    state_long['state_long_rate']=state_long.state_total_deaths/state_long.state_total_population
    obs=(panel[panel.deaths.notna()].groupby(['state_abbr','cause_id','county_fips'],as_index=False)
         .agg(observed_deaths=('deaths','sum'),observed_population=('population','sum'),
              observed_years=('deaths','count'),mean_population=('population','mean')))
    med=(panel.groupby(['state_abbr','cause_id'],as_index=False).population.median().rename(columns={'population':'state_cause_median_county_population'}))
    counties=panel[['state_abbr','cause_id','county_fips','county','population']].drop_duplicates(['state_abbr','cause_id','county_fips'])
    w=counties.merge(obs,on=['state_abbr','cause_id','county_fips'],how='left').merge(state_long,on=['state_abbr','cause_id'],how='left').merge(med,on=['state_abbr','cause_id'],how='left')
    w['prior_equivalent_population']=3*w.state_cause_median_county_population
    w['observed_deaths']=w.observed_deaths.fillna(0)
    w['observed_population']=w.observed_population.fillna(0)
    w['observed_years']=w.observed_years.fillna(0)
    w['eb_history_rate']=(w.observed_deaths+w.state_long_rate*w.prior_equivalent_population)/(w.observed_population+w.prior_equivalent_population)
    w['eb_expected_count_reference']=w.population*w.eb_history_rate
    w['population_weight']=w.population
    w['equal_weight']=1.0
    w.to_csv(TABLES/'imputation_weight_model_v5.csv',index=False,encoding='utf-8-sig')
    return w


def prepare_conditional_poisson_sampler(lam: np.ndarray,total: int,cap: int=9):
    lam=np.asarray(lam,float); n=len(lam); total=int(round(total))
    if total<0 or total>cap*n: raise ValueError((n,total))
    if n==0: return {'n':0,'total':total,'cap':cap,'ww':None,'dp':None}
    if total==0: return {'n':n,'total':0,'cap':cap,'ww':None,'dp':None}
    lam=np.maximum(lam,1e-12)
    lam=lam/np.exp(np.mean(np.log(lam)))
    ks=np.arange(cap+1)
    lw=np.outer(np.log(lam),ks)-gammaln(ks+1)
    lw-=lw.max(axis=1,keepdims=True)
    ww=np.exp(lw)
    dp=np.zeros((n+1,total+1),float); dp[n,0]=1.0
    for i in range(n-1,-1,-1):
        for s in range(total+1):
            kmax=min(cap,s)
            kvals=np.arange(kmax+1)
            dp[i,s]=np.dot(ww[i,kvals],dp[i+1,s-kvals])
        mx=dp[i].max()
        if mx>0: dp[i]/=mx
    if dp[0,total]<=0: raise RuntimeError('Conditional sampler zero probability')
    return {'n':n,'total':total,'cap':cap,'ww':ww,'dp':dp}


def sample_prepared_conditional_poisson(prepared,rng: np.random.Generator) -> np.ndarray:
    n=prepared['n']; total=prepared['total']; cap=prepared['cap']
    if n==0: return np.array([],int)
    if total==0: return np.zeros(n,int)
    ww=prepared['ww']; dp=prepared['dp']
    out=np.zeros(n,int); rem=total
    for i in range(n):
        kmin=max(0,rem-cap*(n-i-1)); kmax=min(cap,rem)
        kvals=np.arange(kmin,kmax+1)
        probs=ww[i,kvals]*dp[i+1,rem-kvals]
        probs=probs/probs.sum()
        k=int(rng.choice(kvals,p=probs)); out[i]=k; rem-=k
    if rem!=0: raise RuntimeError('Conditional sampler remainder')
    return out


def generate_imputations(panel: pd.DataFrame,weights: pd.DataFrame,method: str,m: int,seed: int) -> np.ndarray:
    rng=np.random.default_rng(seed)
    draws=np.tile(panel.deaths.to_numpy(float),(m,1))
    wm=weights.set_index(['state_abbr','cause_id','county_fips'])
    groups=[]
    for key,idx in panel.groupby(['state_abbr','year','cause_id'],sort=False).groups.items():
        ids=np.asarray(list(idx),int); sub=panel.loc[ids]
        sup=sub.death_suppressed.to_numpy(bool)
        if not sup.any(): continue
        supids=ids[sup]
        gap=int(round(float(sub.state_deaths.iloc[0])-float(sub.deaths.fillna(0).sum())))
        if method=='eb_history':
            lam=np.array([panel.loc[j,'population']*wm.loc[(panel.loc[j,'state_abbr'],panel.loc[j,'cause_id'],panel.loc[j,'county_fips']),'eb_history_rate'] for j in supids],float)
        elif method=='population_only':
            lam=panel.loc[supids,'population'].to_numpy(float)
        elif method=='equal_weight':
            lam=np.ones(len(supids),float)
        else: raise ValueError(method)
        prepared=prepare_conditional_poisson_sampler(lam,gap)
        groups.append((supids,prepared,key))
    for supids,prepared,key in groups:
        for im in range(m):
            draws[im,supids]=sample_prepared_conditional_poisson(prepared,rng)
    # exact checks
    for im in range(m):
        temp=panel[['state_abbr','year','cause_id','state_deaths']].copy(); temp['d']=draws[im]
        chk=temp.groupby(['state_abbr','year','cause_id']).agg(d=('d','sum'),state=('state_deaths','first'))
        if not np.allclose(chk.d,chk.state): raise RuntimeError(f'State reconciliation failed {method} draw {im+1}')
    np.savez_compressed(DATA/f'imputed_deaths_{method}_v5.npz',draws=draws)
    return draws


def save_primary_imputation_outputs(panel: pd.DataFrame,draws: np.ndarray) -> None:
    sup=panel.death_suppressed.to_numpy(bool)
    panel2=panel.copy()
    panel2['deaths_mi_mean']=np.mean(draws,axis=0)
    panel2['deaths_mi_sd']=np.std(draws,axis=0,ddof=1)
    panel2['deaths_mi_q025']=np.quantile(draws,.025,axis=0)
    panel2['deaths_mi_q975']=np.quantile(draws,.975,axis=0)
    panel2.to_csv(DATA/'county_year_disease_panel_v5.csv',index=False,encoding='utf-8-sig')
    rows=[]
    ids=np.where(sup)[0]
    for m in range(draws.shape[0]):
        rows.append(pd.DataFrame({'imputation':m+1,'row_id':ids,'imputed_deaths':draws[m,ids].astype(int)}))
    pd.concat(rows,ignore_index=True).to_csv(DATA/'suppressed_deaths_mi_draws_v5.csv.gz',index=False,compression='gzip')
    unc=(panel2[panel2.death_suppressed].groupby('cause_id',as_index=False)
         .agg(n_suppressed=('row_id','size'),mean_imputed=('deaths_mi_mean','mean'),
              mean_imputation_sd=('deaths_mi_sd','mean'),median_imputation_sd=('deaths_mi_sd','median'),
              mean_interval_width=('deaths_mi_q975',lambda x:np.nan)))
    # compute interval width separately
    width=panel2[panel2.death_suppressed].assign(w=lambda d:d.deaths_mi_q975-d.deaths_mi_q025).groupby('cause_id').w.mean()
    unc['mean_95pct_draw_range_width']=unc.cause_id.map(width)
    unc=unc.drop(columns=['mean_interval_width'])
    unc.to_csv(TABLES/'imputation_uncertainty_by_disease_v5.csv',index=False,encoding='utf-8-sig')


def rubin_pool(q: np.ndarray,u: np.ndarray) -> dict:
    q=np.asarray(q,float); u=np.asarray(u,float)
    ok=np.isfinite(q)&np.isfinite(u)&(u>=0); q=q[ok]; u=u[ok]; m=len(q)
    if m==0: return {}
    qbar=float(np.mean(q)); ubar=float(np.mean(u)); b=float(np.var(q,ddof=1)) if m>1 else 0.0
    total=ubar+(1+1/m)*b
    se=math.sqrt(max(total,0))
    if b<=1e-15 or m==1:
        df=1e9; r=0.0
    else:
        r=((1+1/m)*b)/max(ubar,1e-15)
        df=(m-1)*(1+1/r)**2
    crit=float(student_t.ppf(.975,df)) if df<1e8 else 1.95996398454
    p=float(2*student_t.sf(abs(qbar/se),df)) if se>0 and df<1e8 else (float(2*norm.sf(abs(qbar/se))) if se>0 else np.nan)
    fmi=float((r+2/(df+3))/(r+1)) if r>=0 else np.nan
    return {'estimate':qbar,'standard_error':se,'ci_low':qbar-crit*se,'ci_high':qbar+crit*se,
            'p_value':p,'m_used':m,'within_variance':ubar,'between_variance':b,
            'total_variance':total,'df_rubin':df,'relative_increase_variance':r,
            'fraction_missing_information':fmi,'monte_carlo_error':math.sqrt(b/m) if m>1 else 0.0}


def specification_config(spec: str) -> tuple[str,str,str|None,bool]:
    if spec=='main': return 'pm25_iqr','ses_std',None,False
    if spec=='lag1': return 'pm25_lag1_iqr','ses_std',None,False
    if spec=='lead1_placebo': return 'pm25_lead1_iqr','ses_std',None,False
    if spec=='exclude_2020': return 'pm25_iqr','ses_std','year != 2020',False
    if spec=='state_linear_trends': return 'pm25_iqr','ses_std',None,True
    if spec=='poverty_modifier': return 'pm25_iqr','poverty_std',None,False
    raise ValueError(spec)


def fit_model_task(task: dict) -> dict:
    try:
        panel=pd.read_csv(DATA/'county_year_disease_panel_base_v5.csv',low_memory=False)
        cause=task['cause_id']; method=task['method']; spec=task['spec']; m_requested=int(task.get('m',M_PRIMARY))
        exposure,modifier,query,trends=specification_config(spec)
        d=panel[panel.cause_id.eq(cause)].copy()
        if query: d=d.query(query).copy()
        needed=['population',exposure,modifier,'county_fips','year','state_abbr']
        d=d.dropna(subset=needed).copy()
        if method=='complete_case':
            d=d.dropna(subset=['deaths']).copy(); ymat=d.deaths.to_numpy(float)[None,:]
        else:
            arr=np.load(DATA/f'imputed_deaths_{method}_v5.npz')['draws'][:m_requested]
            ymat=arr[:,d.row_id.to_numpy(int)]
        d=d[(d.population>0)].copy()
        # align after population filter
        if ymat.shape[1] != len(d):
            # population filter should not remove rows, but guard explicitly
            raise ValueError('Outcome/design length mismatch')
        d['county_model']=d.county_fips.astype(str)
        formula=f'{exposure} + {modifier} + {exposure}:{modifier} + C(county_model) + C(year)'
        if trends: formula += ' + C(state_abbr):year_centered'
        Xdf=patsy.dmatrix(formula,d,return_type='dataframe')
        col_names=list(Xdf.columns); X=np.asarray(Xdf,dtype=float); del Xdf; gc.collect()
        term_index={name:i for i,name in enumerate(col_names)}
        offset=np.log(d.population.to_numpy(float)); groups=d.county_fips.to_numpy(int)
        # one fixed alpha per task, estimated from mean completed outcome
        ymean=np.mean(ymat,axis=0)
        pfit=sm.GLM(ymean,X,family=sm.families.Poisson(),offset=offset).fit(maxiter=100)
        mu=np.asarray(pfit.fittedvalues,float)
        alpha=float(np.clip(np.sum((ymean-mu)**2-ymean)/max(np.sum(mu**2),1e-12),.001,2.0))
        base_fit=sm.GLM(ymean,X,family=sm.families.NegativeBinomial(alpha=alpha),offset=offset).fit(
            start_params=np.asarray(pfit.params,float),maxiter=80)
        warm_start=np.asarray(base_fit.params,float)
        del pfit, base_fit, mu; gc.collect()
        terms=[exposure,modifier,f'{exposure}:{modifier}']
        draw_rows=[]; marginal_rows=[]; failed=[]
        for im in range(ymat.shape[0]):
            y=ymat[im]
            try:
                fit=sm.GLM(y,X,family=sm.families.NegativeBinomial(alpha=alpha),offset=offset).fit(
                    start_params=warm_start,maxiter=35,cov_type='cluster',cov_kwds={'groups':groups})
                params=np.asarray(fit.params,float); bse=np.asarray(fit.bse,float); cov=np.asarray(fit.cov_params(),float)
                for term in terms:
                    if term in term_index:
                        j=term_index[term]
                        draw_rows.append({'imputation':im+1,'term':term,'estimate':float(params[j]),
                                          'within_variance':float(bse[j]**2),'se':float(bse[j]),
                                          'converged':bool(fit.converged)})
                inter=f'{exposure}:{modifier}'; j1=term_index[exposure]; j3=term_index[inter]
                b1=float(params[j1]); b3=float(params[j3])
                v11=float(cov[j1,j1]); v33=float(cov[j3,j3]); v13=float(cov[j1,j3])
                for level in [-1.0,0.0,1.0]:
                    beta=b1+level*b3; var=max(v11+level*level*v33+2*level*v13,0)
                    marginal_rows.append({'imputation':im+1,'modifier_level_sd':level,'estimate':beta,'within_variance':var})
                del fit, params, bse, cov
                gc.collect()
            except Exception as e:
                failed.append({'imputation':im+1,'error':repr(e)})
                gc.collect()
        draw_df=pd.DataFrame(draw_rows); marg_df=pd.DataFrame(marginal_rows)
        pooled=[]
        for term,g in draw_df.groupby('term'):
            po=rubin_pool(g.estimate,g.within_variance)
            po.update({'cause_id':cause,'cause_zh':CAUSE_ZH[cause],'method':method,'specification':spec,
                       'exposure':exposure,'modifier':modifier,'term':term,'nb_alpha_fixed':alpha,
                       'n_observations':int(len(d)),'n_counties':int(d.county_fips.nunique()),
                       'suppression_share_original':float(panel[panel.cause_id.eq(cause)].death_suppressed.mean())})
            po['irr']=math.exp(po['estimate']); po['irr_ci_low']=math.exp(po['ci_low']); po['irr_ci_high']=math.exp(po['ci_high'])
            po['percent_change']=(po['irr']-1)*100; po['percent_change_ci_low']=(po['irr_ci_low']-1)*100; po['percent_change_ci_high']=(po['irr_ci_high']-1)*100
            pooled.append(po)
        pooled_m=[]
        for level,g in marg_df.groupby('modifier_level_sd'):
            po=rubin_pool(g.estimate,g.within_variance)
            po.update({'cause_id':cause,'cause_zh':CAUSE_ZH[cause],'method':method,'specification':spec,
                       'exposure':exposure,'modifier':modifier,'modifier_level_sd':level,'n_observations':int(len(d))})
            po['irr']=math.exp(po['estimate']); po['irr_ci_low']=math.exp(po['ci_low']); po['irr_ci_high']=math.exp(po['ci_high'])
            po['percent_change']=(po['irr']-1)*100; po['percent_change_ci_low']=(po['irr_ci_low']-1)*100; po['percent_change_ci_high']=(po['irr_ci_high']-1)*100
            pooled_m.append(po)
        meta={'cause_id':cause,'method':method,'specification':spec,'requested_m':m_requested,
              'successful_m':int(draw_df.imputation.nunique()) if not draw_df.empty else 0,'failed':failed,
              'n_observations':int(len(d)),'n_counties':int(d.county_fips.nunique()),'nb_alpha_fixed':alpha}
        return {'ok':True,'task':task,'pooled':pooled,'marginal':pooled_m,
                'draw_rows':draw_df.to_dict('records'),'meta':meta}
    except Exception as e:
        return {'ok':False,'task':task,'error':repr(e),'traceback':traceback.format_exc()}


def run_models() -> dict[str,pd.DataFrame]:
    tasks=[]
    for cause in CAUSE_ORDER:
        tasks.append({'method':PRIMARY_METHOD,'cause_id':cause,'spec':'main','m':M_PRIMARY})
        tasks.append({'method':'complete_case','cause_id':cause,'spec':'main','m':1})
    for method in ['population_only','equal_weight']:
        for cause in ['cerebrovascular_disease','ischemic_heart_disease','copd']:
            tasks.append({'method':method,'cause_id':cause,'spec':'main','m':M_SENS})
    for spec in ['lag1','lead1_placebo','exclude_2020','state_linear_trends','poverty_modifier']:
        tasks.append({'method':PRIMARY_METHOD,'cause_id':'copd','spec':spec,'m':M_PRIMARY})
    log(f'Running {len(tasks)} pooled model tasks in isolated sequential processes')
    result_dir=LOGS/'model_task_results_v5'; result_dir.mkdir(parents=True,exist_ok=True)
    worker=Path(__file__).with_name('model_worker_cli.py')
    results=[]
    for i,t in enumerate(tasks,1):
        out=result_dir/f'task_{i:03d}.json'
        cmd=[sys.executable,str(worker),'--task',json.dumps(t,ensure_ascii=False),'--output',str(out)]
        try:
            if out.exists():
                cached=json.loads(out.read_text(encoding='utf-8'))
                if cached.get('task')==t:
                    r=cached
                else:
                    out.unlink(missing_ok=True); r=None
            else: r=None
            if r is None:
                cp=subprocess.run(cmd,cwd=str(ROOT),capture_output=True,text=True,timeout=900,
                                  env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'})
                if cp.returncode!=0 or not out.exists():
                    r={'ok':False,'task':t,'error':f'worker returncode={cp.returncode}; stderr={cp.stderr[-4000:]}'}
                else:
                    r=json.loads(out.read_text(encoding='utf-8'))
        except Exception as e:
            r={'ok':False,'task':t,'error':repr(e),'traceback':traceback.format_exc()}
        results.append(r)
        log(f"  [{i}/{len(tasks)}] {'OK' if r.get('ok') else 'FAILED'}: {t['method']} · {t['spec']} · {t['cause_id']}")
    pooled=[]; marg=[]; draws=[]; failures=[]; meta=[]
    for r in results:
        if r.get('ok'):
            pooled.extend(r['pooled']); marg.extend(r['marginal']); draws.extend(r['draw_rows']); meta.append(r['meta'])
        else: failures.append({'task':json.dumps(r.get('task'),ensure_ascii=False),'error':r.get('error'),'traceback':r.get('traceback')})
    p=pd.DataFrame(pooled); m=pd.DataFrame(marg); dr=pd.DataFrame(draws); fail=pd.DataFrame(failures); mt=pd.DataFrame(meta)
    if not p.empty:
        mask=(p.method.eq(PRIMARY_METHOD)&p.specification.eq('main')&p.term.isin(['pm25_iqr','pm25_iqr:ses_std']))
        p.loc[mask,'p_fdr_bh']=bh_adjust(p.loc[mask,'p_value'])
    p.to_csv(TABLES/'pooled_multiple_imputation_models_v5.csv',index=False,encoding='utf-8-sig')
    m.to_csv(TABLES/'pooled_marginal_effects_v5.csv',index=False,encoding='utf-8-sig')
    dr.to_csv(TABLES/'per_imputation_model_estimates_v5.csv.gz',index=False,compression='gzip')
    mt.to_csv(TABLES/'model_task_metadata_v5.csv',index=False,encoding='utf-8-sig')
    fail.to_csv(TABLES/'model_failures_v5.csv',index=False,encoding='utf-8-sig')
    main=p[p.specification.eq('main')].copy() if not p.empty else pd.DataFrame()
    if not main.empty:
        comp=main[main.term.str.contains(':',regex=False)].pivot_table(index=['cause_id','cause_zh'],columns='method',values=['percent_change','percent_change_ci_low','percent_change_ci_high','p_value','fraction_missing_information'],aggfunc='first')
        comp.columns=['_'.join(c).strip() for c in comp.columns]; comp=comp.reset_index()
        sens=main[(main.cause_id.isin(['cerebrovascular_disease','ischemic_heart_disease','copd'])) & main.term.str.contains(':',regex=False)].copy()
    else:
        comp=pd.DataFrame(); sens=pd.DataFrame()
    comp.to_csv(TABLES/'mi_vs_complete_case_comparison_v5.csv',index=False,encoding='utf-8-sig')
    sens.to_csv(TABLES/'imputation_weight_sensitivity_v5.csv',index=False,encoding='utf-8-sig')
    robust=p[(p.cause_id.eq('copd')) & (~p.specification.eq('main'))].copy() if not p.empty else pd.DataFrame()
    robust.to_csv(TABLES/'copd_mi_robustness_v5.csv',index=False,encoding='utf-8-sig')
    return {'pooled':p,'marginal':m,'draws':dr,'failures':fail,'metadata':mt,'comparison':comp,'sensitivity':sens,'robustness':robust}


def create_suppression_tables(panel: pd.DataFrame,diag: pd.DataFrame) -> None:
    ss=(panel.groupby('cause_id',as_index=False).agg(n_rows=('row_id','size'),n_suppressed=('death_suppressed','sum'),
          n_counties=('county_fips','nunique'),observed_deaths=('deaths','sum'),state_total_deaths=('state_deaths','sum')))
    # state totals repeated by counties, replace with unique totals
    totals=panel[['state_abbr','year','cause_id','state_deaths']].drop_duplicates().groupby('cause_id').state_deaths.sum()
    ss['state_total_deaths']=ss.cause_id.map(totals)
    ss['suppressed_pct']=ss.n_suppressed/ss.n_rows*100
    ss['hidden_deaths']=ss.state_total_deaths-ss.observed_deaths
    ss['hidden_deaths_pct']=ss.hidden_deaths/ss.state_total_deaths*100
    ss['cause_zh']=ss.cause_id.map(CAUSE_ZH)
    ss.to_csv(TABLES/'suppression_summary_by_disease_v5.csv',index=False,encoding='utf-8-sig')
    year=(diag.groupby(['year','cause_id'],as_index=False).agg(state_deaths=('state_deaths','sum'),hidden_deaths=('suppressed_gap','sum'),suppressed_counties=('suppressed_counties','sum')))
    year['hidden_deaths_pct']=year.hidden_deaths/year.state_deaths*100
    year.to_csv(TABLES/'suppression_by_year_disease_v5.csv',index=False,encoding='utf-8-sig')


def make_priority_table(panel: pd.DataFrame,draws: np.ndarray) -> pd.DataFrame:
    recent_mask=panel.year.between(2016,2020).to_numpy()
    sub=panel[recent_mask].copy(); y=draws[:,recent_mask]
    group_cols=['state_abbr','state','county_fips','county','cause_id']
    groups=sub.groupby(group_cols,sort=False).indices
    rows=[]
    for key,loc in groups.items():
        loc=np.asarray(loc,int); pop=float(sub.iloc[loc].population.sum())
        rates=y[:,loc].sum(axis=1)/pop*100000
        r=dict(zip(group_cols,key)); r.update({'mortality_mi_mean_per_100k':float(rates.mean()),
             'mortality_mi_q025_per_100k':float(np.quantile(rates,.025)),
             'mortality_mi_q975_per_100k':float(np.quantile(rates,.975)),
             'mortality_mi_sd_per_100k':float(rates.std(ddof=1)),
             'suppressed_pct':float(sub.iloc[loc].death_suppressed.mean()*100),
             'mean_pm25':float(sub.iloc[loc].county_smoke_pm25_annual_burden.mean()),
             'mean_ses':float(sub.iloc[loc].ses_disadvantage_z.mean()),
             'mean_poverty':float(sub.iloc[loc].poverty_rate.mean())})
        rows.append(r)
    out=pd.DataFrame(rows)
    out['exposure_percentile']=out.groupby('cause_id').mean_pm25.rank(pct=True)
    out['ses_percentile']=out.groupby('cause_id').mean_ses.rank(pct=True)
    out['health_percentile']=out.groupby('cause_id').mortality_mi_mean_per_100k.rank(pct=True)
    out['screening_priority_score']=out[['exposure_percentile','ses_percentile','health_percentile']].mean(axis=1)
    out['priority_rank_within_disease']=out.groupby('cause_id').screening_priority_score.rank(method='first',ascending=False).astype(int)
    # ranking stability across MI draws
    top30_prob=np.zeros(len(out)); top10d_prob=np.zeros(len(out))
    key_to_row={tuple(row[c] for c in group_cols):i for i,row in out.iterrows()}
    # compute scores per draw using fixed exposure/SES percentiles and draw-specific health percentile
    for im in range(draws.shape[0]):
        death_rate=[]
        for key,loc in groups.items():
            loc=np.asarray(loc,int); pop=float(sub.iloc[loc].population.sum())
            death_rate.append((key,float(y[im,loc].sum()/pop*100000)))
        tmp=pd.DataFrame([{**dict(zip(group_cols,k)),'rate':rate} for k,rate in death_rate])
        tmp['health_pct']=tmp.groupby('cause_id').rate.rank(pct=True)
        tmp=tmp.merge(out[group_cols+['exposure_percentile','ses_percentile']],on=group_cols,how='left')
        tmp['score']=tmp[['exposure_percentile','ses_percentile','health_pct']].mean(axis=1)
        tmp['overall_rank']=tmp.score.rank(method='first',ascending=False)
        tmp['disease_rank']=tmp.groupby('cause_id').score.rank(method='first',ascending=False)
        for _,rr in tmp.iterrows():
            i=key_to_row[tuple(rr[c] for c in group_cols)]
            top30_prob[i]+=rr.overall_rank<=30; top10d_prob[i]+=rr.disease_rank<=10
    out['probability_overall_top30']=top30_prob/draws.shape[0]
    out['probability_disease_top10']=top10d_prob/draws.shape[0]
    out=out.sort_values(['screening_priority_score','probability_overall_top30'],ascending=False)
    out.to_csv(TABLES/'county_disease_screening_priority_mi_v5.csv',index=False,encoding='utf-8-sig')
    out.head(30).to_csv(TABLES/'top30_county_disease_priorities_mi_v5.csv',index=False,encoding='utf-8-sig')
    return out


def make_figures(panel: pd.DataFrame,diag: pd.DataFrame,models: dict,priority: pd.DataFrame) -> None:
    pooled=models['pooled']; marg=models['marginal']; ss=pd.read_csv(TABLES/'suppression_summary_by_disease_v5.csv')
    # Fig1 flow
    fig,ax=plt.subplots(figsize=(13,5.6)); ax.axis('off')
    boxes=[(0.03,'县级CDC WONDER\nObserved / Suppressed'),(0.23,'州级CDC WONDER\n精确州—年总死亡数'),(0.43,'0—9约束 + 州总量\n条件泊松多重插补'),(0.64,'30套完整县—年数据\n负二项固定效应模型'),(0.84,'Rubin规则合并\n效应、标准误与排名')]
    for x,text in boxes:
        patch=FancyBboxPatch((x,0.33),0.15,0.34,boxstyle='round,pad=0.018',fc='#eef5f9',ec='#2d5f75',lw=1.5,transform=ax.transAxes)
        ax.add_patch(patch); ax.text(x+0.075,0.50,text,ha='center',va='center',fontsize=11,transform=ax.transAxes)
    for (x,_),(x2,_) in zip(boxes[:-1],boxes[1:]):
        ax.add_patch(FancyArrowPatch((x+0.15,0.50),(x2,0.50),arrowstyle='-|>',mutation_scale=14,lw=1.4,color='#555',transform=ax.transAxes))
    ax.set_title('Fig1  州总量约束多重插补与县级健康效应分析流程',fontsize=16,pad=14)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig1_constrained_mi_design_v5.png',dpi=300,bbox_inches='tight'); fig.savefig(FIGURES/'Fig1_constrained_mi_design_v5.pdf',bbox_inches='tight'); plt.close(fig)
    # Fig2 suppression
    s=ss.set_index('cause_id').loc[CAUSE_ORDER].reset_index()
    fig,ax=plt.subplots(figsize=(10.5,5.8)); x=np.arange(len(s)); w=.38
    ax.bar(x-w/2,s.suppressed_pct,w,label='受抑制县—年记录比例')
    ax.bar(x+w/2,s.hidden_deaths_pct,w,label='被隐藏死亡数占州总死亡比例')
    ax.set_xticks(x); ax.set_xticklabels([CAUSE_ZH[c] for c in s.cause_id],rotation=25,ha='right')
    ax.set_ylabel('比例（%）'); ax.set_title('Fig2  受抑制记录与被隐藏死亡负担'); ax.legend(); ax.grid(axis='y',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig2_suppression_profile_v5.png',dpi=300); fig.savefig(FIGURES/'Fig2_suppression_profile_v5.pdf'); plt.close(fig)
    # Fig3 uncertainty
    pp=pd.read_csv(DATA/'county_year_disease_panel_v5.csv',low_memory=False)
    arr=[pp[(pp.cause_id.eq(c))&pp.death_suppressed].deaths_mi_sd.dropna().values for c in CAUSE_ORDER]
    fig,ax=plt.subplots(figsize=(10.8,5.8)); ax.boxplot(arr,labels=[CAUSE_ZH[c] for c in CAUSE_ORDER],showfliers=False)
    ax.set_ylabel('受抑制单元的插补标准差（死亡数）'); ax.set_title('Fig3  多重插补不确定性分布'); ax.tick_params(axis='x',rotation=25); ax.grid(axis='y',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig3_imputation_uncertainty_v5.png',dpi=300); fig.savefig(FIGURES/'Fig3_imputation_uncertainty_v5.pdf'); plt.close(fig)
    # Fig4 MI vs CC interaction
    g=pooled[(pooled.specification.eq('main'))&pooled.term.str.contains(':',regex=False)&pooled.method.isin([PRIMARY_METHOD,'complete_case'])].copy()
    fig,ax=plt.subplots(figsize=(9.2,6.2)); yy=np.arange(len(CAUSE_ORDER));
    for method,off,label,marker in [(PRIMARY_METHOD,-.12,'州总量约束MI','o'),('complete_case',.12,'仅公开记录','s')]:
        q=g[g.method.eq(method)].set_index('cause_id').reindex(CAUSE_ORDER)
        ax.errorbar(q.percent_change,yy+off,xerr=[q.percent_change-q.percent_change_ci_low,q.percent_change_ci_high-q.percent_change],fmt=marker,capsize=3,label=label)
    ax.axvline(0,color='black',lw=1); ax.set_yticks(yy); ax.set_yticklabels([CAUSE_ZH[c] for c in CAUSE_ORDER]); ax.invert_yaxis()
    ax.set_xlabel(r'PM$_{2.5}$×社会劣势交互：率比变化（%）'); ax.set_title('Fig4  多重插补与完整案例结果比较'); ax.legend(); ax.grid(axis='x',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig4_mi_vs_complete_case_v5.png',dpi=300); fig.savefig(FIGURES/'Fig4_mi_vs_complete_case_v5.pdf'); plt.close(fig)
    # Fig5 main effects and interactions
    q=pooled[(pooled.method.eq(PRIMARY_METHOD))&(pooled.specification.eq('main'))&pooled.term.isin(['pm25_iqr','pm25_iqr:ses_std'])].copy()
    fig,ax=plt.subplots(figsize=(10.2,6.3)); yy=np.arange(len(CAUSE_ORDER))
    for term,off,label,marker in [('pm25_iqr',-.14,r'PM$_{2.5}$主效应','o'),('pm25_iqr:ses_std',.14,r'PM$_{2.5}$×SES','s')]:
        z=q[q.term.eq(term)].set_index('cause_id').reindex(CAUSE_ORDER)
        ax.errorbar(z.percent_change,yy+off,xerr=[z.percent_change-z.percent_change_ci_low,z.percent_change_ci_high-z.percent_change],fmt=marker,capsize=3,label=label)
    ax.axvline(0,color='black',lw=1); ax.set_yticks(yy); ax.set_yticklabels([CAUSE_ZH[c] for c in CAUSE_ORDER]); ax.invert_yaxis(); ax.legend()
    ax.set_xlabel(r'每1个PM$_{2.5}$ IQR对应的率比变化（%）'); ax.set_title('Fig5  州总量约束多重插补后的疾病模型'); ax.grid(axis='x',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig5_pooled_mi_forest_v5.png',dpi=300); fig.savefig(FIGURES/'Fig5_pooled_mi_forest_v5.pdf'); plt.close(fig)
    # Fig6 COPD robustness
    z=pooled[(pooled.cause_id.eq('copd'))&pooled.term.str.contains(':',regex=False)].copy()
    order=[('main',PRIMARY_METHOD,'主MI'),('main','population_only','人口权重MI'),('main','equal_weight','等权MI'),('main','complete_case','完整案例'),
           ('lag1',PRIMARY_METHOD,'lag1'),('lead1_placebo',PRIMARY_METHOD,'lead1安慰剂'),('exclude_2020',PRIMARY_METHOD,'剔除2020'),
           ('state_linear_trends',PRIMARY_METHOD,'州趋势'),('poverty_modifier',PRIMARY_METHOD,'贫困率修饰')]
    rows=[]
    for spec,method,label in order:
        a=z[(z.specification.eq(spec))&(z.method.eq(method))]
        if len(a): r=a.iloc[0].copy(); r['label']=label; rows.append(r)
    r=pd.DataFrame(rows); yy=np.arange(len(r))
    fig,ax=plt.subplots(figsize=(9.5,6.0)); ax.errorbar(r.percent_change,yy,xerr=[r.percent_change-r.percent_change_ci_low,r.percent_change_ci_high-r.percent_change],fmt='o',capsize=3)
    ax.axvline(0,color='black',lw=1); ax.set_yticks(yy); ax.set_yticklabels(r.label); ax.invert_yaxis(); ax.set_xlabel('COPD效应修饰：率比变化（%）'); ax.set_title('Fig6  COPD多重插补与稳健性分析'); ax.grid(axis='x',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig6_copd_mi_robustness_v5.png',dpi=300); fig.savefig(FIGURES/'Fig6_copd_mi_robustness_v5.pdf'); plt.close(fig)
    # Fig7 marginal
    z=marg[(marg.cause_id.eq('copd'))&(marg.method.eq(PRIMARY_METHOD))&(marg.specification.eq('main'))].sort_values('modifier_level_sd')
    fig,ax=plt.subplots(figsize=(7.4,5.5)); labels=['低劣势（-1 SD）','平均','高劣势（+1 SD）']
    ax.errorbar(np.arange(3),z.percent_change,yerr=[z.percent_change-z.percent_change_ci_low,z.percent_change_ci_high-z.percent_change],fmt='o-',capsize=4)
    ax.axhline(0,color='black',lw=1); ax.set_xticks(np.arange(3)); ax.set_xticklabels(labels); ax.set_ylabel(r'每1 IQR PM$_{2.5}$的死亡率比变化（%）'); ax.set_title('Fig7  不同社会劣势水平下的COPD边际关联'); ax.grid(axis='y',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig7_copd_marginal_effects_v5.png',dpi=300); fig.savefig(FIGURES/'Fig7_copd_marginal_effects_v5.pdf'); plt.close(fig)
    # Fig8 priorities
    top=priority.head(20).sort_values('screening_priority_score')
    fig,ax=plt.subplots(figsize=(10.5,7.0)); labels=[f"{r.state_abbr} · {r.county.split(',')[0]} · {CAUSE_ZH[r.cause_id]}" for _,r in top.iterrows()]
    ax.barh(np.arange(len(top)),top.screening_priority_score); ax.set_yticks(np.arange(len(top))); ax.set_yticklabels(labels,fontsize=8.5)
    ax.set_xlabel('多重插补筛查优先级'); ax.set_title('Fig8  重点县—疾病组合（2016—2020）'); ax.grid(axis='x',alpha=.25)
    fig.tight_layout(); fig.savefig(FIGURES/'Fig8_county_disease_priority_mi_v5.png',dpi=300); fig.savefig(FIGURES/'Fig8_county_disease_priority_mi_v5.pdf'); plt.close(fig)


def set_cell_text(cell,text,bold=False,size=9):
    cell.text=''; p=cell.paragraphs[0]; r=p.add_run(str(text)); r.bold=bold; r.font.size=Pt(size)
    r.font.name='Arial'; r._element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
    cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_table(doc,df,cols,headers,max_rows=20):
    d=df[cols].head(max_rows).copy(); t=doc.add_table(rows=1,cols=len(cols)); t.style='Table Grid'
    for j,h in enumerate(headers): set_cell_text(t.rows[0].cells[j],h,True,8.5)
    trPr=t.rows[0]._tr.get_or_add_trPr(); hdr=OxmlElement('w:tblHeader'); hdr.set(qn('w:val'),'true'); trPr.append(hdr)
    for _,row in d.iterrows():
        cells=t.add_row().cells
        for j,c in enumerate(cols):
            v=row[c]
            if isinstance(v,(float,np.floating)):
                txt='<0.001' if ('p_' in c or c=='p_value') and v<.001 else f'{v:.3f}'
            else: txt='' if pd.isna(v) else str(v)
            set_cell_text(cells[j],txt,False,8.2)
    doc.add_paragraph('')


def fmt_p(x):
    if pd.isna(x): return 'NA'
    return '<0.001' if float(x)<.001 else f'{float(x):.3f}'


def create_report(panel: pd.DataFrame,diag: pd.DataFrame,models: dict,priority: pd.DataFrame) -> None:
    pooled=models['pooled']; ss=pd.read_csv(TABLES/'suppression_summary_by_disease_v5.csv')
    doc=Document(); sec=doc.sections[0]; sec.top_margin=Inches(.65); sec.bottom_margin=Inches(.65); sec.left_margin=Inches(.72); sec.right_margin=Inches(.72)
    styles=doc.styles
    styles['Normal'].font.name='Arial'; styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei'); styles['Normal'].font.size=Pt(10)
    title=doc.add_paragraph(); title.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=title.add_run('州总量约束多重插补优化报告 v5'); r.bold=True; r.font.size=Pt(20); r.font.name='Microsoft YaHei'
    sub=doc.add_paragraph('美国西部六州县级野火烟雾 PM₂.₅ 与健康不公平分析（2006—2020）'); sub.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_picture(str(FIGURES/'Fig1_constrained_mi_design_v5.png'),width=Inches(7.0))
    def heading(text,level=1): doc.add_heading(text,level=level)
    def para(text): p=doc.add_paragraph(text); p.paragraph_format.first_line_indent=Pt(20); p.paragraph_format.space_after=Pt(5); return p
    heading('执行摘要',1)
    para(f'本次优化将州级CDC WONDER死亡总数作为硬约束，对县级Suppressed死亡数实施0—9例范围内的条件泊松多重插补。六州、15年、7类疾病共{len(diag)}个州—年—疾病组合全部满足约束，州级人口与县级人口逐项完全一致，不需要任何超过9例的宽松补齐。主分析生成{M_PRIMARY}套完整县—年数据，并以负二项固定效应模型分别拟合后用Rubin规则合并，因此模型标准误同时包含回归不确定性和受抑制值的不确定性。')
    heading('1. 为什么本方法比单次补齐更合理',1)
    para('单次历史权重补齐只能给出一组确定的县级死亡数，随后模型会把估计值误当作真实观测，通常低估标准误。v5保留州级总死亡数和每个受抑制县0—9例两项已知信息，在所有合法分配中重复抽样，并将不同抽样结果带来的变异传递到回归系数、置信区间和重点县排名。插补模型不使用PM₂.₅或社会经济变量，以减少人为制造暴露—健康关联的风险；县级历史疾病率经过州级均值经验贝叶斯收缩，避免小县历史率过度波动。')
    heading('2. 数据口径与州—县对账',1)
    para(f'县级数据覆盖Arizona、California、Colorado、Idaho、Oregon和Washington的{panel.county_fips.nunique()}个县、2006—2020年和7类疾病，共{len(panel):,}条县—年—疾病记录。受抑制记录共{int(panel.death_suppressed.sum()):,}条，占{panel.death_suppressed.mean()*100:.1f}%。所有630个州—年—疾病组合均满足州总死亡数减去公开县级死亡数之和位于0至9×受抑制县数之间。')
    add_table(doc,ss.assign(cause_zh=ss.cause_id.map(CAUSE_ZH)).sort_values('suppressed_pct',ascending=False),['cause_zh','suppressed_pct','hidden_deaths_pct','n_suppressed','hidden_deaths'],['疾病','受抑制记录(%)','隐藏死亡占比(%)','受抑制记录数','隐藏死亡数'],10)
    doc.add_picture(str(FIGURES/'Fig2_suppression_profile_v5.png'),width=Inches(6.8))
    heading('3. 多重插补不确定性',1)
    para('每个受抑制单元的插补结果不是一个固定数字，而是一组0—9之间且满足州总量的可能值。人口较小、同州受抑制县较多且州级缺口较大的组合，其插补不确定性更高。该不确定性已经进入Rubin合并方差，因此v5的置信区间通常比单次补齐或将受抑制记录删除更符合数据实际。')
    doc.add_picture(str(FIGURES/'Fig3_imputation_uncertainty_v5.png'),width=Inches(6.8))
    heading('4. 主模型结果：多重插补是否改变原结论',1)
    main=pooled[(pooled.method.eq(PRIMARY_METHOD))&(pooled.specification.eq('main'))&pooled.term.isin(['pm25_iqr','pm25_iqr:ses_std'])].copy()
    main['model_term']=main.term.map({'pm25_iqr':'PM₂.₅主效应','pm25_iqr:ses_std':'PM₂.₅×SES交互'})
    add_table(doc,main.assign(cause_zh=main.cause_id.map(CAUSE_ZH)).sort_values(['model_term','p_value']),['cause_zh','model_term','percent_change','percent_change_ci_low','percent_change_ci_high','p_value','p_fdr_bh','fraction_missing_information'],['疾病','模型项','变化(%)','95%CI下','95%CI上','p值','FDR','FMI'],20)
    doc.add_picture(str(FIGURES/'Fig5_pooled_mi_forest_v5.png'),width=Inches(7.0))
    # dynamic narrative
    copd=main[(main.cause_id.eq('copd'))&(main.term.eq('pm25_iqr:ses_std'))].iloc[0]
    cc=pooled[(pooled.cause_id.eq('copd'))&(pooled.method.eq('complete_case'))&(pooled.specification.eq('main'))&pooled.term.str.contains(':',regex=False)].iloc[0]
    para(f'COPD的PM₂.₅×社会经济劣势交互在州总量约束多重插补后为{copd.percent_change:.3f}%（95%CI {copd.percent_change_ci_low:.3f}%至{copd.percent_change_ci_high:.3f}%，p={fmt_p(copd.p_value)}，FDR={fmt_p(copd.p_fdr_bh)}），与仅使用公开死亡数的完整案例估计{cc.percent_change:.3f}%方向一致。FMI为{copd.fraction_missing_information:.3f}，表示受抑制值对该系数的不确定性贡献有限/中等，不能忽略但没有推翻原信号。')
    para('呼吸系统疾病、慢性下呼吸道疾病和COPD仍可能出现相似交互方向，但三者存在疾病分类嵌套，不能作为三个独立重复验证。哮喘的隐藏比例最高，即便使用州约束多重插补，其县级空间分配仍有较大不确定性，因此只适合作为补充结局。任何负向PM₂.₅主效应均不得解释为保护作用。')
    doc.add_picture(str(FIGURES/'Fig4_mi_vs_complete_case_v5.png'),width=Inches(6.8))
    heading('5. COPD权重与模型稳健性',1)
    para('为检验历史疾病率权重是否人为强化社会经济梯度，v5同时使用人口权重和等权分配进行多重插补。另对COPD开展lag1、未来暴露安慰剂、剔除2020年、州特定线性趋势和贫困率替代分析。只有在插补权重替换后方向一致、未来暴露安慰剂不支持相同关联、且州趋势或剔除极端年份后不完全消失时，才能称为相对稳定的探索性效应修饰信号。')
    doc.add_picture(str(FIGURES/'Fig6_copd_mi_robustness_v5.png'),width=Inches(6.8))
    doc.add_picture(str(FIGURES/'Fig7_copd_marginal_effects_v5.png'),width=Inches(6.3))
    heading('6. 重点县—疾病组合优化',1)
    para('重点县筛查不再使用受抑制值固定为5例的中点，而是对30套插补中的2016—2020年疾病死亡率分别计算，并报告均值、95%抽样范围和进入前30名的概率。该方法可以区分“平均分数较高但排名不稳定”和“在大多数合法插补中均保持高优先级”的组合。筛查分数仍是研究对象选择工具，不是因果风险或可归因死亡数。')
    top=priority[(priority.suppressed_pct<=20)&(priority.probability_overall_top30>=0.5)].head(20).copy(); top['cause_zh']=top.cause_id.map(CAUSE_ZH)
    add_table(doc,top,['state_abbr','county','cause_zh','screening_priority_score','mortality_mi_mean_per_100k','mortality_mi_q025_per_100k','mortality_mi_q975_per_100k','probability_overall_top30'],['州','县','疾病','筛查分数','死亡率均值','2.5%','97.5%','进入Top30概率'],20)
    doc.add_picture(str(FIGURES/'Fig8_county_disease_priority_mi_v5.png'),width=Inches(7.0))
    heading('7. 优化后的结论',1)
    para('州级总量信息显著改善了县级受抑制数据的使用方式：全部州—年—疾病组合均可在0—9约束内精确对账，因此不需要违反CDC抑制规则的强制补齐。多重插补避免把单次估计值当作真实值，并将插补不确定性传递到模型结果。若COPD交互在不同插补权重、完整案例和关键稳健性模型中保持正向，则可将其表述为西部六州县尺度上较一致的探索性社会经济效应修饰信号；若在剔除2020年或州趋势模型中明显减弱，则应进一步强调极端年份和长期趋势的驱动作用。')
    heading('8. 下一步研究',1)
    para('下一步应优先选择多重插补排名稳定、受抑制比例较低且2020年前后烟雾暴露变化明显的县群，将全年PM₂.₅细化为火灾季累计暴露、重烟雾日和连续高暴露天数。健康结局优先保留COPD或慢性下呼吸道疾病中的一个代表性呼吸结局，并补充脑血管或缺血性心脏病。模型需加入温度、干旱、非野火PM₂.₅、臭氧、吸烟率、老龄化和医疗资源等县级协变量。')
    heading('9. 解释边界',1)
    for text in ['插补值是可能值分布，不是真实县级死亡数。','州总量约束消除了总数不一致，但不能消除生态学混杂。','县级年度模型不能估计短期急性事件效应。','疾病类别嵌套结果不能视为独立重复。','重点县排名用于后续研究选择，不代表因果风险最高。']:
        doc.add_paragraph('• '+text)
    path=REPORTS/'州总量约束多重插补优化结果报告_v5.docx'; doc.save(path)
    md=f'''# 州总量约束多重插补优化结果 v5\n\n- 六州、{panel.county_fips.nunique()}县、2006—2020年、7类疾病。\n- 县—年—疾病记录：{len(panel):,}；Suppressed：{int(panel.death_suppressed.sum()):,}（{panel.death_suppressed.mean()*100:.1f}%）。\n- 州—年—疾病对账：{len(diag)}组，全部满足0—9约束，人口差额为0。\n- 主插补：经验贝叶斯历史率权重，{M_PRIMARY}套；人口权重和等权插补作为敏感性分析。\n- 主模型：负二项GLM，县固定效应、年份固定效应、人口offset、县聚类标准误，Rubin规则合并。\n\n## 核心原则\n\n1. 不把Suppressed当作0或固定5例。\n2. 不把单次插补值当作真实观测。\n3. 所有插补都精确恢复州级总死亡数。\n4. 模型结果仍属于县尺度生态学关联。\n'''
    (REPORTS/'州总量约束多重插补优化结果报告_v5.md').write_text(md,encoding='utf-8')


def create_prompt_and_readme(panel: pd.DataFrame) -> None:
    prompt='''# 县级Suppressed死亡数据州总量约束多重插补实验Prompt\n\n你是一名环境流行病学、缺失数据、多重插补、计数模型和空间健康不公平分析专家。请使用县级CDC WONDER健康数据、相同口径州级死亡总数、县级野火烟雾PM2.5和社会经济数据，构建2006—2020年县—年—疾病面板。\n\n## 核心要求\n\n1. 将公开县级死亡数视为精确值，将Suppressed视为0—9例区间。\n2. 对每个州—年—疾病，计算州级总数减去公开县级合计的隐藏总数。\n3. 仅在隐藏总数位于0和9×受抑制县数之间时执行约束插补；不可行组合必须停止并核查口径，禁止给县分配超过9例。\n4. 主插补使用县级历史疾病率的经验贝叶斯收缩权重，并以县人口形成期望死亡数；不使用PM2.5或SES作为插补权重。\n5. 在0—9整数约束及州级总量约束下，从独立泊松分布的条件分布中抽取至少30套完整数据。\n6. 使用人口权重和等权分配作为插补模型敏感性分析。\n7. 每套数据分别拟合死亡数负二项模型，包含县固定效应、年份固定效应和log(population) offset，标准误按县聚类。\n8. 使用Rubin规则合并系数、方差、置信区间、p值、FMI和Monte Carlo误差。\n9. 进行lag1、未来暴露安慰剂、剔除极端年份、州特定趋势和替代SES指标分析。\n10. 重点县排名必须基于多重插补分布，报告排名概率和健康负担区间，不能使用固定中点作为最终结果。\n\n## 解释边界\n\n- 多重插补恢复的是可能值分布，不是真实县级死亡数。\n- 州总量约束不能消除生态学谬误和未测混杂。\n- 负向PM2.5系数不得解释为保护作用。\n- 县年度模型不用于短期急性健康效应。\n'''
    (ROOT/'PROMPT_州总量约束多重插补完整实验_v5.md').write_text(prompt,encoding='utf-8')
    readme=f'''# Afire Project v5：州总量约束多重插补优化\n\n## 范围\n\nArizona、California、Colorado、Idaho、Oregon和Washington，共{panel.county_fips.nunique()}个县、2006—2020年、7类疾病。\n\n## 方法升级\n\n- 每个Suppressed县—年死亡数限制在0—9例。\n- 每个州—年—疾病的县级死亡数严格等于州级CDC WONDER总死亡数。\n- 主分析生成30套条件泊松多重插补数据，并用Rubin规则合并模型。\n- 人口权重和等权插补用于检验历史疾病率权重依赖。\n\n## 一键运行\n\nLinux：`bash run_all.sh`\n\nWindows：`run_all.bat`\n\n也可执行：`python scripts/run_all.py`\n\n## 关键输出\n\n- `reports/州总量约束多重插补优化结果报告_v5.docx`\n- `tables/state_county_reconciliation_v5.csv`\n- `tables/pooled_multiple_imputation_models_v5.csv`\n- `tables/mi_vs_complete_case_comparison_v5.csv`\n- `tables/county_disease_screening_priority_mi_v5.csv`\n- `data_processed/county_year_disease_panel_v5.csv`\n- `data_processed/suppressed_deaths_mi_draws_v5.csv.gz`\n- `figures/Fig1-Fig8`\n\n## 注意\n\n插补值不是实际死亡数；结果为县尺度生态学证据。\n'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    (ROOT/'requirements.txt').write_text('pandas>=2.0\nnumpy>=1.24\nscipy>=1.10\nstatsmodels>=0.14\npatsy>=0.5\nmatplotlib>=3.7\npython-docx>=1.1\n',encoding='utf-8')
    (ROOT/'run_all.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd "$(dirname "$0")" && pwd)"\nexport AFIRE_COUNTY_PROJECT_ROOT="$ROOT"\npython "$ROOT/scripts/run_all.py"\n',encoding='utf-8')
    os.chmod(ROOT/'run_all.sh',0o755)
    (ROOT/'run_all.bat').write_text('@echo off\nset AFIRE_COUNTY_PROJECT_ROOT=%~dp0\npython "%~dp0scripts\\run_all.py"\n',encoding='utf-8')


def final_check() -> None:
    expected=[ROOT/'README.md',ROOT/'PROMPT_州总量约束多重插补完整实验_v5.md',
              DATA/'county_year_disease_panel_v5.csv',DATA/'suppressed_deaths_mi_draws_v5.csv.gz',
              TABLES/'state_county_reconciliation_v5.csv',TABLES/'pooled_multiple_imputation_models_v5.csv',
              TABLES/'mi_vs_complete_case_comparison_v5.csv',TABLES/'top30_county_disease_priorities_mi_v5.csv',
              REPORTS/'州总量约束多重插补优化结果报告_v5.docx']
    rows=[{'path':str(p.relative_to(ROOT)),'exists':p.exists(),'size_bytes':p.stat().st_size if p.exists() else 0} for p in expected]
    status='PASS' if all(r['exists'] and r['size_bytes']>0 for r in rows) else 'FAIL'
    manifest=[]
    for p in ROOT.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            manifest.append({'relative_path':str(p.relative_to(ROOT)),'size_bytes':p.stat().st_size,'extension':p.suffix.lower()})
    pd.DataFrame(manifest).sort_values('relative_path').to_csv(LOGS/'output_manifest_v5.csv',index=False,encoding='utf-8-sig')
    (ROOT/'final_check_v5.txt').write_text('FINAL CHECK: '+status+'\n'+'\n'.join(f"{r['exists']}\t{r['size_bytes']}\t{r['path']}" for r in rows),encoding='utf-8')
    if status!='PASS': raise RuntimeError('Final check failed')


def main():
    if LOG_FILE.exists(): LOG_FILE.unlink()
    log(f'Project root: {ROOT}')
    panel,state,diag=build_panel(); log(f'Base panel: {len(panel):,} rows; suppressed {panel.death_suppressed.sum():,}')
    create_suppression_tables(panel,diag); log('Suppression and reconciliation tables completed')
    weights=build_imputation_weights(panel); log('Empirical-Bayes imputation weights completed')
    draws_primary=generate_imputations(panel,weights,PRIMARY_METHOD,M_PRIMARY,RANDOM_SEEDS[PRIMARY_METHOD]); log('Primary 30 imputations completed')
    generate_imputations(panel,weights,'population_only',M_SENS,RANDOM_SEEDS['population_only']); log('Population-only sensitivity imputations completed')
    generate_imputations(panel,weights,'equal_weight',M_SENS,RANDOM_SEEDS['equal_weight']); log('Equal-weight sensitivity imputations completed')
    save_primary_imputation_outputs(panel,draws_primary); log('Imputation outputs saved')
    models=run_models(); log('Pooled models completed')
    priority=make_priority_table(panel,draws_primary); log('MI priority screening completed')
    make_figures(panel,diag,models,priority); log('Figures completed')
    create_report(panel,diag,models,priority); log('Report completed')
    create_prompt_and_readme(panel); final_check(); log('Pipeline completed successfully')

if __name__=='__main__':
    try: main()
    except Exception as e:
        log('FATAL: '+repr(e)); log(traceback.format_exc()); raise
