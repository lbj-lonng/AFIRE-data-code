"""Read-only data-schema and manuscript inspection for this scope revision."""
from environment import ROOT,PREV,AUD
import pandas as pd, json
from docx import Document
base=PREV/'02_source_data/full_results'
for name in ['unique_county_year_descriptive','suppression_flags','county_map_values','annual','state_year_exposure_verified','state_year_exposure_all51','state_year','state_county_bridge_90','validation','outcome_dictionary','diagnostics_7outcomes','design']:
    df=pd.read_csv(base/(name+'.csv'))
    print(name,len(df),df.columns.tolist())
    if 'year' in df:print('years',df.year.min(),df.year.max())
    if name in ['validation','outcome_dictionary']:print(df.to_string(index=False))
v=pd.read_csv(ROOT.parents[1]/'paper_package_verified_20260908/paper_package_verified_20260908/data/result2/pseudo_suppression_predictions.csv')
print('VALIDATION',v.shape,v.method.unique(),v.year.min(),v.year.max(),v.cause_id.unique())
d=Document(PREV/'05_manuscripts/Main_Text_CN_clean.docx')
texts=[]
for i,p in enumerate(d.paragraphs):
    txt=''.join(p._p.xpath('.//w:t/text() | .//m:t/text()'))
    texts.append(dict(index=i,style=p.style.name,text=txt,math=len(p._p.xpath('.//m:oMath')),drawing=len(p._p.xpath('.//w:drawing'))))
(AUD/'main_paragraphs.json').write_text(json.dumps(texts,ensure_ascii=False,indent=2),encoding='utf-8')
print('main paragraphs',len(texts))
