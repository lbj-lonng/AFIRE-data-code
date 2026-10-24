from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pandas as pd
import numpy as np
import run_all as r
panel=pd.read_csv(r.DATA/'county_year_disease_panel_base_v5.csv',low_memory=False)
diag=pd.read_csv(r.TABLES/'state_county_reconciliation_v5.csv')
pooled=pd.read_csv(r.TABLES/'pooled_multiple_imputation_models_v5.csv')
marg=pd.read_csv(r.TABLES/'pooled_marginal_effects_v5.csv')
draws=pd.read_csv(r.TABLES/'per_imputation_model_estimates_v5.csv.gz')
meta=pd.read_csv(r.TABLES/'model_task_metadata_v5.csv')
fail_path=r.TABLES/'model_failures_v5.csv'
try: failures=pd.read_csv(fail_path)
except Exception: failures=pd.DataFrame(columns=['task','error','traceback'])
priority=pd.read_csv(r.TABLES/'county_disease_screening_priority_mi_v5.csv')
reliable=priority[(priority.suppressed_pct<=20)&(priority.probability_overall_top30>=0.5)].copy()
reliable.head(30).to_csv(r.TABLES/'top30_low_suppression_priorities_v5.csv',index=False,encoding='utf-8-sig')
models={'pooled':pooled,'marginal':marg,'draws':draws,'failures':failures,'metadata':meta,
        'comparison':pd.read_csv(r.TABLES/'mi_vs_complete_case_comparison_v5.csv'),
        'sensitivity':pd.read_csv(r.TABLES/'imputation_weight_sensitivity_v5.csv'),
        'robustness':pd.read_csv(r.TABLES/'copd_mi_robustness_v5.csv')}
r.make_figures(panel,diag,models,priority)
r.create_report(panel,diag,models,priority)
r.create_prompt_and_readme(panel)
r.final_check()
print('FINALIZATION PASS')
