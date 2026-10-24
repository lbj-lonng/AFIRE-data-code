"""Rebuild this reporting version only. No fitting, sampling or new inference."""
from environment import ROOT,AUD
import subprocess,sys,json,time

def main():
    scripts=['prepare_scope_data.py','audit_allocations.py','plot_figure_1.py','plot_figure_2.py','plot_figure_3.py','plot_figure_4.py','plot_supplement.py','build_main.py','revise_supplement.py','finalize.py','write_delivery.py','render_documents.py','verify_delivery.py']
    log=[]
    for name in scripts:
        started=time.time();print('Running',name,flush=True)
        r=subprocess.run([sys.executable,str(ROOT/'scripts'/name)],cwd=ROOT)
        log.append({'script':name,'returncode':r.returncode,'seconds':round(time.time()-started,3)})
        (AUD/'rebuild_execution.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
        if r.returncode:raise SystemExit(r.returncode)
    if (AUD/'visual_review.csv').exists():
        subprocess.run([sys.executable,str(ROOT/'scripts/seal_delivery.py')],cwd=ROOT,check=True)
    print('Rebuilt from frozen records. Final visual approval is hash-specific; changed pages require review.',flush=True)
if __name__=='__main__':main()
