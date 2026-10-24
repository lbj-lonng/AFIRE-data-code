"""Check exported figures and regenerate generously bounded QA panel crops."""
from pathlib import Path
import sys,json,hashlib,re,platform
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,r'C:\Users\86189\Documents\Codex\2026-09-10\ban\work\pydeps')
import numpy,pandas,matplotlib,pymupdf as fitz
rows=[]
for n in [8,9,10]:
    stem=f'Supplementary_Figure_{n}'
    align=json.loads((ROOT/'audit'/f'{stem}_alignment.json').read_text())
    text=json.loads((ROOT/'audit'/f'{stem}_text.json').read_text())
    collisions=json.loads((ROOT/'audit'/f'{stem}_collisions.json').read_text())
    assert align['verdict']=='PASS' and collisions['verdict']=='PASS'
    assert text['auditable'] and text['below_minimum_count']==0
    doc=fitz.open(ROOT/'figures'/f'{stem}.pdf');p=doc[0]
    assert len(doc)==1
    w,h=p.rect.width*25.4/72,p.rect.height*25.4/72
    assert abs(w-179)<.01 and abs(h-230)<.01
    years=set(map(int,re.findall(r'\b20[012]\d\b',p.get_text())))
    assert all(2009<=x<=2020 for x in years)
    for panel in align['layout']['panels']:
        x0,y0,x1,y1=panel['bbox_pt'];margin=72/25.4
        box=fitz.Rect(max(0,x0-18*margin),max(0,p.rect.height-y1-11*margin),min(p.rect.width,x1+5*margin),min(p.rect.height,p.rect.height-y0+16*margin))
        p.get_pixmap(matrix=fitz.Matrix(220/72,220/72),clip=box).save(ROOT/'previews'/f'{stem}_{panel["id"]}.png')
    rows.append({'figure':n,'width_mm':w,'height_mm':h,'panels':len(align['layout']['panels']),'alignment':'PASS','collisions':'PASS','minimum_font_pt':text['minimum_found_pt'],'text_below_minimum':0})
    doc.close()
en=(ROOT/'Additional_content_EN.md').read_text(encoding='utf-8')
caps=re.split(r'### Supplementary Fig\. \d+[^\n]*\n',en)[1:]
counts=[]
for cap in caps:
    cap=re.sub(r'!\[[^\]]*\]\([^)]*\)','',cap)
    counts.append(len(cap.split()))
assert len(counts)==3 and max(counts)<=350
protected=json.loads((ROOT/'audit/source_sha256_before_after.json').read_text())
assert protected['all_protected_inputs_unchanged']
for path,sha in protected['files'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha
environment={'python':platform.python_version(),'numpy':numpy.__version__,'pandas':pandas.__version__,'matplotlib':matplotlib.__version__,'PyMuPDF':fitz.VersionBind}
(ROOT/'audit/runtime.json').write_text(json.dumps(environment,indent=2),encoding='utf-8')
(ROOT/'scripts/requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in environment.items() if k!='python')+'\n',encoding='utf-8')
(ROOT/'audit/final_machine_checks.json').write_text(json.dumps({'figures':rows,'English_caption_word_counts':dict(zip([8,9,10],counts)),'protected_source_files_unchanged':len(protected['files']),'observation_years_in_figures_valid':True},indent=2),encoding='utf-8')
manifest=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and p.name!='delivery_sha256.csv':
        manifest.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
pandas.DataFrame(manifest).to_csv(ROOT/'audit/delivery_sha256.csv',index=False,encoding='utf-8-sig')
print(json.dumps({'figures':rows,'caption_words':counts,'protected_files':len(protected['files']),'environment':environment},indent=2))
