from __future__ import annotations
import hashlib, json, os, subprocess, sys
from pathlib import Path
import pandas as pd
ROOT=Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT',Path(__file__).resolve().parents[1])); TABLES=ROOT/'tables'; LOGS=ROOT/'logs'

def sha(path:Path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()
checks=[]
def add(name,passed,observed,expected,severity='error'):
 checks.append({'check':name,'status':'PASS' if passed else 'FAIL','observed':str(observed),'expected':str(expected),'severity':severity})
required=['README.md','实施指导_Linux_v6_3.md','setup_linux.sh','run_quick_check_linux.sh','run_full_linux.sh','download_missing_official_linux.sh','scripts/prepare_integrated_data_v6_3.py','scripts/run_one_model_checkpointed_v6_3.py','data_processed/county_year_disease_panel_v6_3.csv','data_external/processed/census_county_year_six_states_2009_2020.csv','tables/integrated_data_coverage_v6_3.csv','tables/screening_models_mean_mi_v6_3.csv']
for rel in required: add('required_'+rel,(ROOT/rel).exists(),(ROOT/rel).exists(),True)
add('no_private_census_key',not (ROOT/'config/census_api_key.env').exists(),(ROOT/'config/census_api_key.env').exists(),False)
census=pd.read_csv(ROOT/'data_external/processed/census_county_year_six_states_2009_2020.csv')
add('census_rows',len(census)==3072,len(census),3072); add('census_counties',census.county_fips.nunique()==256,census.county_fips.nunique(),256); add('census_years',census.year.nunique()==12,census.year.nunique(),12); add('age65_complete',census.age65_share.notna().mean()>=.99,census.age65_share.notna().mean(),'>=0.99'); add('density_complete',census.population_density_km2.notna().mean()>=.99,census.population_density_km2.notna().mean(),'>=0.99')
panel=pd.read_csv(ROOT/'data_processed/county_year_disease_panel_v6_3.csv',low_memory=False)
add('analysis_panel_rows',len(panel)==26880,len(panel),26880); add('analysis_panel_counties',panel.county_fips.nunique()==256,panel.county_fips.nunique(),256); add('analysis_panel_years',panel.year.nunique()==15,panel.year.nunique(),15)
cov=pd.read_csv(ROOT/'tables/integrated_data_coverage_v6_3.csv'); covmap=dict(zip(cov.variable,cov.coverage_pct)); add('drought_coverage_100',covmap.get('drought_fireseason_D1',0)>=99,covmap.get('drought_fireseason_D1',0),'>=99'); add('air_marked_partial',covmap.get('pm25_annual_mean',100)<95,covmap.get('pm25_annual_mean'),'<95')
status=pd.read_csv(ROOT/'tables/screening_model_status_v6_3.csv'); add('screening_completed_9',(status.status=='completed').sum()==9,(status.status=='completed').sum(),9); add('optional_models_blocked_3',(status.status=='blocked_missing_real_covariates').sum()==3,(status.status=='blocked_missing_real_covariates').sum(),3)
# Compile current v6.3 scripts and validate shell syntax.
py_files=[ROOT/'scripts/prepare_integrated_data_v6_3.py',ROOT/'scripts/run_available_models_v6_3.py',ROOT/'scripts/run_one_model_v6_3.py',ROOT/'scripts/run_one_model_checkpointed_v6_3.py',ROOT/'scripts/run_one_screening_v6_3.py',ROOT/'scripts/aggregate_models_v6_3.py',ROOT/'scripts/aggregate_screening_v6_3.py',ROOT/'scripts/generate_status_report_v6_3.py']
compile_ok=True; compile_errors=[]
import py_compile
for p in py_files:
 try: py_compile.compile(str(p),doraise=True)
 except Exception as e: compile_ok=False; compile_errors.append(f'{p.name}:{e}')
add('python_syntax',compile_ok,';'.join(compile_errors) if compile_errors else 'all passed','all passed')
shells=['setup_linux.sh','run_quick_check_linux.sh','run_full_linux.sh','download_missing_official_linux.sh']
shell_ok=True; shell_errors=[]
for rel in shells:
 r=subprocess.run(['bash','-n',str(ROOT/rel)],capture_output=True,text=True)
 if r.returncode: shell_ok=False; shell_errors.append(rel+':'+r.stderr)
add('shell_syntax',shell_ok,';'.join(shell_errors) if shell_errors else 'all passed','all passed')
manifest=[]
for rel in required:
 p=ROOT/rel
 if p.exists() and p.is_file(): manifest.append({'path':rel,'size_bytes':p.stat().st_size,'sha256':sha(p)})
pd.DataFrame(manifest).to_csv(TABLES/'key_file_manifest_v6_3.csv',index=False,encoding='utf-8-sig')
result=pd.DataFrame(checks); result.to_csv(ROOT/'final_check_v6_3.csv',index=False,encoding='utf-8-sig'); summary={'status':'PASS' if (result.loc[result.severity.eq('error'),'status']=='PASS').all() else 'FAIL','checks':len(result),'failed':int((result.status=='FAIL').sum())}; (LOGS/'final_check_v6_3.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(result.to_string(index=False)); print(summary)
if summary['status']!='PASS': raise SystemExit(1)
