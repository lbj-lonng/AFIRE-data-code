from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import pandas as pd

ROOT = Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
from run_available_models_v6_3 import prepare, fit_spec

OUT = ROOT / 'logs' / 'model_results_v6_3'
OUT.mkdir(parents=True, exist_ok=True)

SPECS = [
    dict(name='M1_baseline_SES_fixed_2006_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std'], year_min=2006, year_max=2020),
    dict(name='M2_Census_adjusted_2009_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63'], year_min=2009, year_max=2020),
    dict(name='M3_Census_state_year_FE_2009_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + C(county_model) + C(state_year)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63'], year_min=2009, year_max=2020),
    dict(name='M4_Census_drought_adjusted_2009_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63'], year_min=2009, year_max=2020),
    dict(name='M5_exclude_2020_Census_drought', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63'], year_min=2009, year_max=2019),
    dict(name='M6_timevarying_SES_2010_2020', rhs='pm25_iqr + ses_timevarying_std + pm25_iqr:ses_timevarying_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_timevarying_std'], required=['pm25_iqr','ses_timevarying_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63'], year_min=2010, year_max=2020),
    dict(name='M7_lag1_Census_drought_2010_2020', rhs='pm25_lag1_iqr + pm25_lag1_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)', terms=['pm25_lag1_iqr','pm25_lag1_iqr:ses_baseline_std'], required=['pm25_lag1_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63'], year_min=2010, year_max=2020),
    dict(name='M8_lead1_placebo_Census_drought_2009_2019', rhs='pm25_lead1_iqr + pm25_lead1_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)', terms=['pm25_lead1_iqr','pm25_lead1_iqr:ses_baseline_std'], required=['pm25_lead1_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63'], year_min=2009, year_max=2019),
    dict(name='M9_three_state_air_sensitivity_2009_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + pm25_total_std_v63 + ozone_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63','pm25_total_std_v63','ozone_std_v63'], year_min=2009, year_max=2020, filter_fn=lambda d: d['state_abbr'].isin(['ID','OR','WA'])),
    dict(name='M10_temperature_adjusted_2009_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + temp_fs_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63','temp_fs_std_v63'], year_min=2009, year_max=2020),
    dict(name='M11_full_environment_six_state_2009_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + temp_fs_std_v63 + pm25_total_std_v63 + ozone_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63','temp_fs_std_v63','pm25_total_std_v63','ozone_std_v63'], year_min=2009, year_max=2020),
    dict(name='M12_smoking_sensitivity_2018_2020', rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + smoking_std_v63 + C(county_model) + C(year_model)', terms=['pm25_iqr','pm25_iqr:ses_baseline_std'], required=['pm25_iqr','ses_baseline_std','age65_std_v63','density_std_v63','drought_d1_fs_std_v63','smoking_std_v63'], year_min=2018, year_max=2020),
]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--index',type=int,required=True); args=ap.parse_args()
    spec=SPECS[args.index-1]; name=spec['name']; print(name,flush=True)
    data,draws=prepare()
    try:
        pooled, per, failures, meta=fit_spec(data,draws,**spec)
        pooled.to_csv(OUT/f'{args.index:02d}_{name}_pooled.csv',index=False,encoding='utf-8-sig')
        per.to_csv(OUT/f'{args.index:02d}_{name}_per.csv.gz',index=False,compression='gzip')
        failures.to_csv(OUT/f'{args.index:02d}_{name}_failures.csv',index=False,encoding='utf-8-sig')
        (OUT/f'{args.index:02d}_{name}_status.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        inter=pooled[pooled.term.str.contains(':',regex=False)]
        if not inter.empty:
            r=inter.iloc[0]; print(f'interaction={r.percent_change:.3f}% p={r.p_value:.5g}',flush=True)
    except Exception as e:
        meta={'specification':name,'status':'failed','reason':repr(e)}
        (OUT/f'{args.index:02d}_{name}_status.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Model unavailable or failed: {e}', flush=True)
if __name__=='__main__': main()
