"""Verify read-only historical sources, separately flagging recorded external author changes."""
from pathlib import Path
import csv,hashlib,json
OUT=Path(__file__).resolve().parents[1]
AUD=OUT/'audit'

def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    event_path=AUD/'maintext_sync_history/concurrent_change.json'
    event=json.loads(event_path.read_text(encoding='utf-8')) if event_path.exists() else {}
    sources={}
    for filename in ['history_source_manifest.csv','upstream_history_sources.csv']:
        for r in read(AUD/filename):sources.setdefault(r['path'],r['sha256'])
    rows=[]
    for path,before in sources.items():
        p=Path(path);after=hashlib.sha256(p.read_bytes()).hexdigest()
        status='PASS_UNCHANGED' if before==after else 'FAIL_CHANGED'
        if path==event.get('source') and before==event.get('previous_source_sha256') and after==event.get('new_source_sha256'):status='SOURCE_EXTERNAL_CHANGE_RECORDED'
        rows.append({'path':path,'sha256_initial':before,'sha256_after':after,'status':status,'agent_source_write':False})
    with (AUD/'history_original_files_hash_check.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({'files':len(rows),'unchanged':sum(r['status']=='PASS_UNCHANGED' for r in rows),'source_external_change_recorded':sum(r['status']=='SOURCE_EXTERNAL_CHANGE_RECORDED' for r in rows),'unexpected_change':sum(r['status']=='FAIL_CHANGED' for r in rows)},ensure_ascii=False))

if __name__=='__main__':main()
