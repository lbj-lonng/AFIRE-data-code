"""Read-only historical manuscript inventory; all generated artifacts stay in OUT."""
from pathlib import Path
from lxml import etree
import csv, hashlib, json, zipfile, difflib, re

ROOT=Path(r'D:\postgraduate\wildfire\9.10')
OUT=ROOT/'9.15/AFIRE_Supplement_integrated_20260916_230522'
BASE=ROOT/'9.15/AFIRE_2009_2020_five_outcomes_20260915_194616'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
AUD=OUT/'audit'
EX=AUD/'history_text'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extract_docx(p):
    with zipfile.ZipFile(p) as z:
        root=etree.fromstring(z.read('word/document.xml'))
        paras=[''.join(e.xpath('.//w:t/text() | .//m:t/text()',namespaces=NS)) for e in root.xpath('//w:body//w:p',namespaces=NS)]
        comments=[]
        if 'word/comments.xml' in z.namelist():
            for e in etree.fromstring(z.read('word/comments.xml')).xpath('//w:comment',namespaces=NS):
                cid=e.get('{'+NS['w']+'}id')
                anchors=root.xpath('//w:p[.//w:commentRangeStart[@w:id="'+cid+'"]]',namespaces=NS)
                comments.append({'id':cid,'author':e.get('{'+NS['w']+'}author'),'date':e.get('{'+NS['w']+'}date'),'text':''.join(e.xpath('.//w:t/text()',namespaces=NS)),'anchor':[''.join(a.xpath('.//w:t/text()',namespaces=NS)) for a in anchors]})
        changes=[]
        for tag in ['ins','del','moveFrom','moveTo']:
            for e in root.xpath('//w:'+tag,namespaces=NS):
                changes.append({'tag':tag,'author':e.get('{'+NS['w']+'}author'),'date':e.get('{'+NS['w']+'}date'),'text':''.join(e.xpath('.//w:t/text() | .//w:delText/text()',namespaces=NS))})
        return paras,comments,changes

def run():
    EX.mkdir(parents=True,exist_ok=True)
    versions=[p for p in ROOT.iterdir() if p.is_dir() and (p.name.startswith('AFIRE_') or p.name.startswith('paper_package_'))]
    versions += [p for p in (ROOT/'9.15').iterdir() if p.is_dir() and p!=OUT]
    files=[ROOT/'AFIRE_Supplementary_Methods_CN.docx']
    for v in versions:
        for p in v.rglob('*'):
            if not p.is_file() or p.suffix.lower() not in {'.md','.docx','.tex'}:continue
            rel=p.relative_to(v).as_posix()
            if any(s in p.parts for s in ['_work','node_modules','site-packages','__pycache__']):continue
            if any(s in rel for s in ['audit/inputs/','review/packet/']):continue
            if re.search(r'(Supplement|supplement|unresolved|statistical_adjustment|scope_config|state_source|health_pair|Final|FINAL|README|model.*formula|source.*audit)',p.name,re.I) or p in [BASE/'submission/Main_Text_CN_2009_2020_five_outcomes_clean.docx',BASE/'submission/Main_Text_CN_2009_2020_five_outcomes_highlight.docx']:
                files.append(p)
    files=sorted(set(p for p in files if p.exists()))
    manifest=[];seen={};texts={}
    for i,p in enumerate(files):
        digest=sha(p);duplicate=seen.get(digest,'');seen.setdefault(digest,str(p))
        text='';comments=[];changes=[]
        if p.suffix.lower()=='.docx':
            paras,comments,changes=extract_docx(p);text='\n'.join(f'{j}: {t}' for j,t in enumerate(paras))
        else:text=p.read_text(encoding='utf-8-sig',errors='replace')
        dest=EX/f'{i:03d}_{p.stem}.txt'
        if not duplicate:dest.write_text(text,encoding='utf-8');texts[str(p)]=str(dest)
        manifest.append({'path':str(p),'modified':p.stat().st_mtime,'size':p.stat().st_size,'sha256':digest,'duplicate_of':duplicate,'extracted_text':str(dest) if not duplicate else '', 'comment_count':len(comments),'tracked_change_count':len(changes)})
        if comments or changes or p.name.startswith('Main_Text_CN_2009'):
            (EX/f'{i:03d}_{p.stem}_review.json').write_text(json.dumps({'source':str(p),'sha256':digest,'paragraphs':paras,'comments':comments,'tracked_changes':changes},ensure_ascii=False,indent=2),encoding='utf-8')
    with (AUD/'history_source_manifest.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(manifest[0]));w.writeheader();w.writerows(manifest)
    # Archive directory only; never execute or unpack an old generator.
    zip_path=ROOT/'Afire_paper_handoff_20260825.zip'
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as z:
            listings=[{'member':i.filename,'bytes':i.file_size} for i in z.infolist()]
            (AUD/'handoff_zip_directory.json').write_text(json.dumps(listings,ensure_ascii=False,indent=2),encoding='utf-8')
    (AUD/'history_extraction_index.json').write_text(json.dumps(texts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(files),'distinct_hashes':len(seen),'current_reviews':[x for x in manifest if Path(x['path']).name.startswith('Main_Text_CN_2009')]},ensure_ascii=False,indent=2))

if __name__=='__main__':run()
