"""Record a user-side source change during integration; never mutate the source."""
from pathlib import Path
import csv, difflib, hashlib, json, shutil, zipfile
from lxml import etree
from sync_maintext_si_links import SOURCE,TARGET,REPLACEMENTS,NS,text

OUT=Path(__file__).resolve().parents[1]
AUD=OUT/'audit'

def paras(p):
    with zipfile.ZipFile(p) as z:
        rt=etree.fromstring(z.read('word/document.xml'))
    return [text(p) for p in rt.xpath('//w:body//w:p',namespaces=NS)]

def main():
    old=json.loads((AUD/'maintext_sync_integrity.json').read_text(encoding='utf-8'))
    now=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if now==old['source_sha256']:
        print('No additional source change since last synchronization.');return
    archive=AUD/'maintext_sync_history';archive.mkdir(exist_ok=True)
    saved=archive/('prior_synced_'+old['source_sha256'][:12]+'.docx')
    if not saved.exists():shutil.copy2(TARGET,saved)
    for name in ['maintext_sync_integrity.json','maintext_changes.json','maintext_changes.md','maintext_si_only.diff','maintext_si_crossrefs.csv']:
        p=AUD/name;dest=archive/(old['source_sha256'][:12]+'_'+name)
        if p.exists() and not dest.exists():shutil.copy2(p,dest)
    prior=[]
    for line in paras(saved):
        for before,after in sorted(REPLACEMENTS.items(),key=lambda it:len(it[1]),reverse=True):line=line.replace(after,before)
        prior.append(line)
    current=paras(SOURCE)
    diff='\n'.join(difflib.unified_diff(prior,current,fromfile='author_source_at_initial_sync',tofile='latest_author_source',lineterm=''))
    (archive/'author_changes_after_initial_sync.diff').write_text(diff,encoding='utf-8')
    record={'event':'source_external_change','previous_source_sha256':old['source_sha256'],'new_source_sha256':now,'new_source_mtime':SOURCE.stat().st_mtime,'source':str(SOURCE),'previous_synced_copy':str(saved),'agent_source_writes':False,'action':'Regenerate minimal-reference copy from latest author source; preserve changes and record this concurrency event.'}
    (archive/'concurrent_change.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(diff)

if __name__=='__main__':main()
