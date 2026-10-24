from __future__ import annotations
import json, os
from pathlib import Path
import pandas as pd
ROOT=Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT',Path(__file__).resolve().parents[1]))
SRC=ROOT/'logs'/'model_results_v6_3'; TABLES=ROOT/'tables'; LOGS=ROOT/'logs'
pooled_files=sorted(SRC.glob('*_pooled.csv')); per_files=sorted(SRC.glob('*_per.csv.gz')); failure_files=sorted(SRC.glob('*_failures.csv')); status_files=sorted(SRC.glob('*_status.json'))
pooled=pd.concat([pd.read_csv(f) for f in pooled_files],ignore_index=True) if pooled_files else pd.DataFrame()
if not pooled.empty:
    mask=pooled.term.astype(str).str.contains(':',regex=False); p=pooled.loc[mask,'p_value'].astype(float); order=p.sort_values().index; m=len(p); adj=pd.Series(index=p.index,dtype=float); vals=p.loc[order].to_numpy()*m/(range(1,m+1)); import numpy as np; vals=np.minimum.accumulate(vals[::-1])[::-1]; adj.loc[order]=np.clip(vals,0,1); pooled.loc[mask,'p_fdr_bh_interactions']=adj
    pooled.to_csv(TABLES/'pooled_available_models_v6_3.csv',index=False,encoding='utf-8-sig')
if per_files:
    pd.concat([pd.read_csv(f) for f in per_files],ignore_index=True).to_csv(TABLES/'per_imputation_available_models_v6_3.csv.gz',index=False,compression='gzip')
fail=[]
for f in failure_files:
    try:
        x=pd.read_csv(f)
        if not x.empty: fail.append(x)
    except pd.errors.EmptyDataError: pass
(pd.concat(fail,ignore_index=True) if fail else pd.DataFrame(columns=['specification','imputation','error'])).to_csv(TABLES/'model_failures_v6_3.csv',index=False,encoding='utf-8-sig')
statuses=[json.loads(f.read_text(encoding='utf-8')) for f in status_files]
pd.DataFrame(statuses).to_csv(TABLES/'model_run_status_v6_3.csv',index=False,encoding='utf-8-sig')
summary={'completed':sum(s.get('status')=='completed' for s in statuses),'failed':sum(s.get('status')=='failed' for s in statuses),'expected':12}
(LOGS/'model_status_v6_3.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(summary)
