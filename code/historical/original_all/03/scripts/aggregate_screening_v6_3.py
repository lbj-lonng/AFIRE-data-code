from pathlib import Path
import json, os, pandas as pd
ROOT=Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT',Path(__file__).resolve().parents[1])); SRC=ROOT/'logs'/'screening_results_v6_3'; TABLES=ROOT/'tables'; LOGS=ROOT/'logs'
files=sorted(SRC.glob('*.csv')); rows=[pd.read_csv(f) for f in files]; pd.concat(rows,ignore_index=True).to_csv(TABLES/'screening_models_mean_mi_v6_3.csv',index=False,encoding='utf-8-sig') if rows else None
stats=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(SRC.glob('*.json'))]; pd.DataFrame(stats).to_csv(TABLES/'screening_model_status_v6_3.csv',index=False,encoding='utf-8-sig'); (LOGS/'screening_status_v6_3.json').write_text(json.dumps({'completed':sum(x.get('status')=='completed' for x in stats),'failed':sum(x.get('status')=='failed' for x in stats),'expected':12},ensure_ascii=False,indent=2),encoding='utf-8'); print(stats)
