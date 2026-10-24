"""Isolated Windows rendering; explicit task-managed portable fallback, no desktop apps."""
from environment import ROOT, SUB, AUD
import os, sys, subprocess, shutil, json, hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
RENDERER=ROOT/'scripts/render_docx_local.py'
SOFFICE=Path('C:/Users/86189/Documents/Codex/2026-09-10/ban/work/libreoffice_renderer/program')
POPPLER=Path('C:/Users/86189/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
assert (SOFFICE/'soffice.exe').exists()
env={**os.environ,'PATH':str(SOFFICE)+os.pathsep+str(POPPLER)+os.pathsep+os.environ['PATH']}
env['PYTHONPATH']=os.pathsep.join(sys.path)
def run(p):
    out=AUD/'render'/p.stem
    if out.exists():
        history=AUD/'render_history';history.mkdir(exist_ok=True)
        target=history/(p.stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        assert out.resolve().is_relative_to(ROOT.resolve()) and target.resolve().is_relative_to(ROOT.resolve())
        out.rename(target)
    out.mkdir(parents=True)
    cmd=[sys.executable,'-X','utf8',str(RENDERER),str(p),'--output_dir',str(out),'--emit_pdf','--verbose']
    r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',env=env)
    (out/'render.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
    pdf=out/(p.stem+'.pdf')
    if r.returncode==0 and pdf.exists():shutil.copy2(pdf,SUB/pdf.name)
    result={'docx':str(p),'returncode':r.returncode,'pages':len(list(out.glob('page-*.png'))),'pdf':str(SUB/pdf.name),'docx_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    (out/'render_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result,flush=True)
    if r.returncode:print(r.stderr[-3000:],flush=True)
    return result
if __name__=='__main__':
    names=sys.argv[1:]
    paths=[SUB/n for n in names] if names else sorted(SUB.glob('*.docx'))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,paths))
    assert all(r['returncode']==0 and r['pages'] for r in results),results
