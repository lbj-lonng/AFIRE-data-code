from environment import ROOT
import json
CONFIG=json.loads((ROOT/'scripts/scope_config.yaml').read_text(encoding='utf-8'))
START=CONFIG['study_start_year'];END=CONFIG['study_end_year'];YEARS=CONFIG['study_years']
IDS=CONFIG['outcomes'];LABELS=CONFIG['labels'];SIX=['AZ','CA','CO','ID','OR','WA']
assert END-START+1==YEARS==12 and len(IDS)==5
def year_subset(df,column='year'):return df[df[column].between(START,END)].copy()
