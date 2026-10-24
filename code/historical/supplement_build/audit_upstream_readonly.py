"""Identity checks only: no estimation, downloads, allocation or source mutation."""
from pathlib import Path
import csv, hashlib, json, re
from lxml import html
ROOT=Path(r'D:\postgraduate\wildfire')
OUT=ROOT/'9.10/9.15/AFIRE_Supplement_integrated_20260916_230522'
PANEL=ROOT/'9.10/paper_package_verified_20260908/paper_package_verified_20260908/data/analysis/county_year_disease_panel_v6_3.csv'
CAUSES=['copd','chronic_lower_respiratory','respiratory_system','circulatory_system','ischemic_heart_disease']
STATES=['04','06','08','16','41','53']
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def num(s):
    try:return float(s)
    except (ValueError,TypeError):return None
def main():
    records=read(PANEL)
    panel={(r['county_fips'].zfill(5),r['year'],r['cause_id']):r for r in records if r['cause_id'] in CAUSES and 2009<=int(r['year'])<=2020}
    state={(r['state_fips'].zfill(2),r['year'],r['cause_id']):r for r in panel.values()}
    files=[PANEL]; checks=[]
    for cause in CAUSES:
        for sf in STATES:
            matches=list((ROOT/'Afire/下载/by_state_cause').glob(f'{sf}_*__{cause}__county_year_*.csv'))
            assert len(matches)==1
            p=matches[0];files.append(p)
            errors=[];rows=[]
            for r in read(p):
                if 2009<=int(r['Year'])<=2020:
                    k=(r['County Code'].zfill(5),r['Year'],cause);q=panel[k];rows.append(k)
                    popcol=next(c for c in r if c.startswith('Population'))
                    ok=(num(r['Deaths'])==num(q['deaths']) and ('suppressed' in r['Deaths'].lower())==(q['death_suppressed']=='True') and num(r[popcol])==num(q['population']) and r['icd10_range']==q['icd10_range'])
                    if not ok:errors.append(k)
            checks.append({'scope':'county_source_to_frozen_panel','cause_id':cause,'state':sf,'n':len(rows),'mismatches':len(errors),'status':'PASS' if not errors else 'FAIL','source':str(p)})
        matches=list((ROOT/'Afire/DATA/health/cdc_wonder_state_year_output').glob(f'*_{cause}_state_year*.csv'))
        assert len(matches)==1
        p=matches[0];files.append(p);errors=[];rows=[]
        for r in read(p):
            scol=next(c for c in r if c.startswith('State_State')); ycol=next(c for c in r if c.startswith('Year_')); dcol=next(c for c in r if c.startswith('Deaths_'));pcol=next(c for c in r if c.startswith('Population_'))
            sf=re.search(r'\((\d\d)\)',r[scol]).group(1)
            if sf in STATES and 2009<=int(r[ycol])<=2020:
                k=(sf,r[ycol],cause);q=state[k];rows.append(k)
                if not (num(r[dcol])==num(q['state_deaths']) and num(r[pcol])==num(q['state_population']) and r['icd10_range']==q['icd10_range']):errors.append(k)
        checks.append({'scope':'state_source_to_frozen_panel','cause_id':cause,'state':'six_states','n':len(rows),'mismatches':len(errors),'status':'PASS' if not errors else 'FAIL','source':str(p)})
    for f in ['README.md','data_dictionary.csv','processing_manifest.csv']:
        files.append(ROOT/'Afire/DATA/ecnomy/NHGIS_SES_simplified'/f)
    files += [ROOT/'Afire/1/scripts/prepare_integrated_data_v6_3.py',ROOT/'Afire/Afire_project_v2/scripts/afire_pipeline.py',ROOT/'Afire/DATA/health/cdc_wonder_state_year_output/query_scope.json']
    b1=Path(r'C:\Users\86189\Documents\Codex\2026-09-10\ban\work\sources\AFIRE_B1_joint_adjustment_20260909_233833\AFIRE_B1_joint_adjustment_20260909_233833')
    weight=ROOT/'Afire/all/03/tables/imputation_weight_model_v5.csv'
    weight_source_manifest=b1/'01_input_audit/input_manifest.csv'
    weight_manifest_row=next(r for r in read(weight_source_manifest) if r['input_id']=='weight_model')
    weight_identity={'source':str(weight),'source_manifest':str(weight_source_manifest),'sha256':sha(weight),'archived_before':weight_manifest_row['sha256_before'],'archived_after':weight_manifest_row['sha256_after'],'status':'PASS' if sha(weight)==weight_manifest_row['sha256_before']==weight_manifest_row['sha256_after'] else 'FAIL','construction_history':'2006–2020; fixed primary rate does not exclude target year','state_rate':'sum of unique state-cause-year deaths / sum of unique state-cause-year population','county_history':'sum deaths and population only in nonmissing death years','prior_exposure':'3 × median county-year population within state-cause across original history','construction_source':str(ROOT/'Afire/1/scripts/run_all.py'),'application_source':str(b1/'run_pipeline.py')}
    (OUT/'audit/upstream_eb_weight_identity.json').write_text(json.dumps(weight_identity,ensure_ascii=False,indent=2),encoding='utf-8')
    files += [weight,weight_source_manifest,b1/'run_pipeline.py',ROOT/'Afire/1/scripts/run_all.py',ROOT/'9.10/paper_package_verified_20260908/paper_package_verified_20260908/scripts/result2/run_innovation_pilot.py',ROOT/'Afire/下载/cdc_wonder_six_states_county_year_2006_2020_package/cdc_wonder_six_states_county_year_package/download_cdc_wonder_six_states_county_year.py']
    snippets=[]
    for p in (ROOT/'Afire/DATA/health/cdc_wonder_state_year_output/raw_responses').glob('*.html'):
        if any(p.stem.endswith('_'+c) for c in CAUSES):
            files.append(p);doc=html.fromstring(p.read_bytes());txt=' '.join(doc.text_content().split())
            for term in ['Query Date','Query Criteria','Accessed at','Date Accessed','Accessed','Citation','2000 U.S.']:
                locations=[m.start() for m in re.finditer(re.escape(term),txt)]
                for ix in locations[-2:]:snippets.append({'source':str(p),'term':term,'snippet':txt[max(ix-70,0):ix+700]})
    with (OUT/'audit/upstream_cdc_identity_checks.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
    manifest=[{'path':str(p),'sha256':sha(p),'size':p.stat().st_size} for p in files]
    with (OUT/'audit/upstream_history_sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(manifest[0]));w.writeheader();w.writerows(manifest)
    (OUT/'audit/upstream_cdc_archived_html_snippets.json').write_text(json.dumps(snippets,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(checks),'all_pass':all(c['status']=='PASS' for c in checks),'county_rows':sum(c['n'] for c in checks if c['scope'].startswith('county')),'state_rows':sum(c['n'] for c in checks if c['scope'].startswith('state'))},ensure_ascii=False))
if __name__=='__main__':main()
