"""Reaggregate descriptive records and saved validation predictions only."""
from environment import ROOT,AUD,SD
from scope import *
import pandas as pd,numpy as np,json,hashlib
IN=AUD/'inputs';T=IN/'tables';OUT=SD/'full_results';OUT.mkdir(exist_ok=True)
COUNTS=[];CHECKS=[]
def read(p):return pd.read_csv(p,dtype={'county_fips':str,'state_fips':str},float_precision='round_trip')
def write(df,name):df.to_csv(OUT/(name+'.csv'),index=False)
def check(name,passed,detail):
    CHECKS.append(dict(check=name,status='PASS' if passed else 'FAIL',detail=detail));assert passed,(name,detail)
def count(name,before,after,rule):COUNTS.append(dict(metric=name,before=before,after=after,rule=rule))
def gini(values):
    a=np.sort(np.asarray(values,float));n=len(a)
    return float(2*np.dot(np.arange(1,n+1),a)/(n*a.sum())-(n+1)/n) if a.sum() else 0.
def run():
    panel=read(IN/'mortality_panel.csv');d=year_subset(panel);d=d[d.cause_id.isin(IDS)].copy()
    d.county_fips=d.county_fips.str.zfill(5);d.state_fips=d.state_fips.str.zfill(2)
    key=['county_fips','year','cause_id'];check('mortality_keys',not d.duplicated(key).any(),len(d))
    check('mortality_coverage',len(d)==15360 and set(d.groupby('cause_id').size())=={3072} and d.groupby('county_fips').size().eq(60).all(),'5 causes × 12 years × 256 counties')
    dic=read(T/'outcome_dictionary.csv').set_index('outcome_id').loc[IDS].reset_index()
    check('ICD_definition',dic.icd10.tolist()==CONFIG['icd10'],dic.icd10.tolist());write(dic,'outcome_dictionary')
    check('suppression_raw_identity',(d.deaths_raw.eq('Suppressed')==d.death_suppressed).all(),'original flags')
    check('public_values_not_missing',d.loc[~d.death_suppressed,'deaths'].notna().all(),'public zero remains zero')
    flags=read(T/'suppression_flags.csv');flags=year_subset(flags);flags=flags[flags.cause_id.isin(IDS)]
    z=d[key+['death_suppressed']].merge(flags,on=key,validate='one_to_one',suffixes=('_raw','_saved'))
    check('flags_match_previous',len(z)==len(d) and z.death_suppressed_raw.eq(z.death_suppressed_saved).all(),len(z))
    cleancols=['state_abbr','county_fips','year','cause_id','icd10_range','deaths','death_suppressed','population','state_deaths','row_id']
    # Count records are aggregated public data; no allocation arrays enter submission.
    write(d[cleancols],'mortality_records')
    groups=[]
    for (state,year,cause),g in d.groupby(['state_abbr','year','cause_id'],sort=True):
        check(f'state_total_unique_{state}_{year}_{cause}',g.state_deaths.nunique()==1,'same public state total')
        hidden=float(g.state_deaths.iloc[0]-g.deaths.sum());supp=int(g.death_suppressed.sum())
        check(f'support_feasible_{state}_{year}_{cause}',supp<=hidden<=9*supp,f'{supp} <= {hidden} <= {9*supp}')
        groups.append(dict(state_abbr=state,year=year,cause_id=cause,n=len(g),suppressed=supp,public_zero=int(g.deaths.eq(0).sum()),public_deaths=float(g.deaths.sum()),hidden_deaths=hidden,state_deaths=float(g.state_deaths.iloc[0])))
    gr=pd.DataFrame(groups);check('state_death_groups',len(gr)==360,len(gr));write(gr,'state_death_remainders')
    sup=gr.groupby('cause_id',sort=False)[['n','suppressed','public_zero','hidden_deaths','state_deaths']].sum().loc[IDS].reset_index()
    sup['record_percent']=sup.suppressed/sup.n*100;sup['hidden_percent']=sup.hidden_deaths/sup.state_deaths*100;write(sup,'suppression')
    count('all_county_cause_records',len(panel),len(d),'year in 2009–2020 and cause whitelist')
    count('suppressed_records',int(panel.death_suppressed.sum()),int(d.death_suppressed.sum()),'count original Suppressed flags after filtering')
    count('public_zero_records',int(panel.deaths.eq(0).sum()),int(d.deaths.eq(0).sum()),'count public deaths==0 after filtering')
    for _,r in sup.iterrows():
        old=read(T/'suppression.csv').set_index('cause_id').loc[r.cause_id]
        for field in ['n','suppressed','public_zero','hidden_deaths','state_deaths','record_percent','hidden_percent']:count(r.cause_id+'_'+field,old[field],r[field],'sum filtered county or unique state groups')
    excols=['state_abbr','county_fips','year','population','baseline_ses_quintile','ses_baseline_std','county_smoke_pm25_annual_burden_y']
    ex=d[excols].drop_duplicates();check('unique_exposure_keys',len(ex)==3072 and not ex.duplicated(['county_fips','year']).any(),len(ex))
    ex=ex.sort_values(['county_fips','year']);write(ex,'county_year_exposure')
    oldmap=read(T/'county_map_values.csv');cmap=oldmap.drop(columns=['n_records','suppressed_records','n_years','n_causes','suppressed_record_percent']).copy()
    cm=d.groupby('county_fips').agg(n_records=('cause_id','size'),suppressed_records=('death_suppressed','sum'),n_years=('year','nunique'),n_causes=('cause_id','nunique')).reset_index()
    cm['suppressed_record_percent']=cm.suppressed_records/cm.n_records*100;cmap=cmap.merge(cm,on='county_fips',validate='one_to_one');write(cmap,'county_map_values')
    xm=ex.groupby('county_fips').county_smoke_pm25_annual_burden_y.mean()
    check('county_means_unchanged',np.allclose(cmap.set_index('county_fips').smoke_mean.sort_index(),xm.sort_index(),rtol=0,atol=1e-12),'existing 2009–2020 means retained')
    for col in ['ses_baseline_std','baseline_ses_quintile']:check('fixed_'+col,ex.groupby('county_fips')[col].nunique().eq(1).all(),'not restandardized or regrouped')
    check('quintile_counts',cmap.groupby('quintile').size().tolist()==[52,51,51,51,51],'frozen groups')
    ann=[]
    for year,g in ex.groupby('year'):
        x=g.county_smoke_pm25_annual_burden_y
        ann.append(dict(year=year,n_counties=len(g),population=g.population.sum(),population_weighted_smoke=np.average(x,weights=g.population),county_mean=x.mean(),county_median=x.median(),county_p10=x.quantile(.1),county_p90=x.quantile(.9),unweighted_county_gini=gini(x)))
    ann=pd.DataFrame(ann);oldann=year_subset(read(T/'annual.csv'))
    check('annual_definitions_unchanged',np.allclose(ann[oldann.columns].to_numpy(),oldann.to_numpy(),rtol=0,atol=1e-8),'reaggregated unique county-years agrees with archived annual summaries');write(ann,'annual')
    write(read(T/'quintiles.csv'),'quintiles')
    state=year_subset(read(T/'state_year_exposure_verified.csv'));check('state_year_coverage',len(state)==588 and not state.duplicated(['state_fips','year']).any(),len(state))
    state=state.drop(columns=['ses_disadvantage_z']);write(state,'state_year_exposure')
    all51=year_subset(read(T/'state_year_exposure_all51.csv')).drop(columns=['ses_disadvantage_z']);write(all51,'state_year_exposure_with_missing')
    check('AK_HI_missing',all51.loc[all51.state_abbr.isin(['AK','HI']),'smoke_pm25_annual_burden'].isna().all(),'not zero')
    sa=year_subset(read(T/'Figure1b_state_annual.csv'));write(sa,'state_annual')
    sm=read(T/'Figure1a_state_map.csv');write(sm,'state_map')
    bridge=year_subset(read(T/'state_county_bridge_90.csv')).drop(columns=['ses_disadvantage_z']);check('bridge_pairs',len(bridge)==72,len(bridge));write(bridge,'state_county_bridge')
    write(year_subset(read(T/'state_year.csv')),'county_aggregated_state_year')
    write(read(T/'within_state_county_distribution.csv'),'within_state_county_distribution')
    econ=read(IN/'state_panels/panel_c.csv');write(econ,'state_baseline_poverty')
    cat=read(IN/'state_panels/top100_catalogue.csv');cat=year_subset(cat,'FIRE_YEAR_INT')
    assignments=year_subset(read(IN/'state_panels/top100_record_state_assignments.csv'))
    check('fire_subset_keys',set(assignments.catalogue_rank)==set(cat.Rank),'all retained records located')
    sourcecounts=read(IN/'state_panels/panel_d.csv')
    fc=assignments.groupby('state').size().rename('catalogue_record_assignments').reset_index().merge(sourcecounts.drop(columns=['catalogue_record_assignments']),on='state',validate='one_to_one').sort_values(['catalogue_record_assignments','state_abbr'],ascending=[False,True])
    write(fc,'fire_state_counts');write(assignments,'fire_record_state_assignments');write(cat,'fire_catalogue_subset')
    cat['normalized_name']=cat.IncidentName.fillna('').astype(str).str.casefold().str.replace(r'[^a-z0-9]','',regex=True)
    dup=cat[cat.normalized_name.ne('') & cat.duplicated(['normalized_name','FIRE_YEAR_INT'],keep=False)].copy();write(dup,'fire_potential_duplicates')
    fire_summary=dict(records=len(cat),assignments=len(assignments),states=len(fc),six_assignments=int(assignments.in_six_state_region.sum()),six_records=assignments.loc[assignments.in_six_state_region,'catalogue_rank'].nunique(),multi_state_records=int((assignments.groupby('catalogue_rank').size()>1).sum()),duplicate_candidates=len(dup),duplicate_groups=dup.groupby(['normalized_name','FIRE_YEAR_INT']).ngroups)
    count('fire_records',100,len(cat),'filter archived catalogue by actual event year; no reranking')
    val0=read(IN/'validation_predictions.csv');val=year_subset(val0);val=val[val.cause_id.isin(IDS)].copy();methods=['equal','population','loyo_fixed_EB','loyo_hierarchical_EB'];vk=['state_abbr','year','cause_id','county_fips']
    check('validation_unique',not val.duplicated(vk+['method']).any(),len(val))
    sets=[set(map(tuple,val[val.method.eq(m)][vk].to_numpy())) for m in methods]
    check('validation_same_evaluation',all(s==sets[0] for s in sets),[len(s) for s in sets])
    check('validation_score_identity',np.allclose(val.absolute_error,(val.posterior_mean-val.true_visible_count).abs(),atol=1e-12) and np.allclose(val.squared_error,(val.posterior_mean-val.true_visible_count)**2,atol=1e-12),'stored per-cell scoring reproduced')
    check('validation_interval_identity',val.interval_covers_truth.eq((val.true_visible_count>=val.q025)&(val.true_visible_count<=val.q975)).all() and np.allclose(val.interval_width,val.q975-val.q025,atol=1e-12),'existing interval endpoints only')
    check('validation_support',val.true_visible_count.between(10,19).all() and set(val.n_draws)=={100} and set(val.support)=={'0-19'},'same saved validation implementation')
    summaries=[]
    for scope,vs in [('all_outcomes',val)]+[(c,val[val.cause_id.eq(c)]) for c in IDS]:
        for method in methods:
            g=vs[vs.method.eq(method)]
            summaries.append(dict(scope=scope,method=method,n_groups=g.pseudo_group_id.nunique(),n_cells=len(g),MAE=g.absolute_error.mean(),RMSE=np.sqrt(g.squared_error.mean()),coverage_95=g.interval_covers_truth.mean(),mean_interval_width=g.interval_width.mean(),mean_CRPS=g.CRPS.mean(),mean_interval_score_95=g.interval_score_95.mean(),year_min=START,year_max=END,n_draws=100,support='0-19'))
    vals=pd.DataFrame(summaries);write(vals,'validation');write(val,'validation_evaluation_records')
    vc=[dict(method=m,original_cells=len(val0[val0.method.eq(m)]),subset_cells=len(val[val.method.eq(m)]),subset_groups=val[val.method.eq(m)].pseudo_group_id.nunique(),same_keys=True,year_min=START,year_max=END,status='PASS') for m in methods]
    pd.DataFrame(vc).to_csv(AUD/'validation_subset_check.csv',index=False)
    health0=read(T/'AFIRE_7outcome_all_results.csv');health=health0[health0.outcome_id.isin(IDS)].copy()
    check('health_models_in_period',health.year_min.ge(START).all() and health.year_max.le(END).all(),len(health))
    check('health_counts',health.groupby('analysis_block').size().to_dict()=={'A':5,'B':25,'C':40,'D':25,'E':40},len(health))
    health=health.drop(columns=['source_path'],errors='ignore');health['comparison_family']=health.comparison_family.replace('A_seven_reference_interactions_Holm','original_Holm_family_n7')
    write(health,'health_results')
    for block,name in [('A','primary'),('B','conditional'),('C','common_sample'),('D','targeted_omissions'),('E','LST_pairs')]:write(health[health.analysis_block.eq(block)],name)
    for c in ['interaction_percent','percent_estimate','CI_percent_lower','CI_percent_upper','percent_CI_lower','percent_CI_upper','beta','SE','P_value','P_adjusted']:
        check('saved_health_'+c,np.array_equal(health[c].to_numpy(),health0.loc[health0.outcome_id.isin(IDS),c].to_numpy(),equal_nan=True),'exact stored values unchanged')
    write(read(T/'design.csv'),'design')
    diag=read(T/'diagnostics_7outcomes.csv');diag=diag[diag.outcome_id.isin(IDS)].drop(columns=['source_path','diagnostic_year_scope','n_public_zero','public_zero_fraction','n_suppressed','suppression_fraction','hidden_death_fraction','mean_hidden_deaths'],errors='ignore');write(diag,'model_diagnostics')
    cond=health[health.analysis_block.eq('B')]
    facts=dict(scope=CONFIG,total_records=len(d),suppressed_records=int(d.death_suppressed.sum()),public_zero_records=int(d.deaths.eq(0).sum()),suppressed_percent=float(d.death_suppressed.mean()*100),state_years=len(state),county_years=len(ex),state_death_groups=len(gr),bridge_pairs=len(bridge),fire=fire_summary,health_rows=len(health),conditional_rows=len(cond),conditional_negative=int((cond.CI_percent_upper<0).sum()),conditional_positive=int((cond.CI_percent_lower>0).sum()),conditional_cross_zero=int(((cond.CI_percent_lower<=0)&(cond.CI_percent_upper>=0)).sum()),validation_cells=len(sets[0]),validation_groups=val.pseudo_group_id.nunique())
    (SD/'scope_facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    pd.DataFrame(COUNTS).to_csv(AUD/'denominator_recalculation.csv',index=False)
    pd.DataFrame(CHECKS).to_csv(AUD/'data_reaggregation_check.csv',index=False)
    print(json.dumps(facts,ensure_ascii=False,indent=2));print(sup.to_string(index=False));print(vals[vals.scope.eq('all_outcomes')].to_string(index=False))
if __name__=='__main__':run()
