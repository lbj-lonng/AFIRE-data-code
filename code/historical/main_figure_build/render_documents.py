"""Run the packaged DOCX renderer with explicit task-managed Windows tools."""
from environment import ROOT
import os,sys,subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
RENDERER=ROOT/'scripts/render_docx_local.py'
# Runtime loader supplies no LibreOffice for Windows. This is the existing task-
# managed portable renderer, not the user's installed desktop LibreOffice.
SOFFICE='C:/Users/86189/Documents/Codex/2026-09-10/ban/work/libreoffice_renderer/program'
POPPLER='C:/Users/86189/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
env={**os.environ,'PATH':SOFFICE+os.pathsep+POPPLER+os.pathsep+os.environ['PATH']}
def run(p):
    out=ROOT/'audit/rendered_pages'/p.stem
    if out.exists():
        history=ROOT/'audit/render_history';history.mkdir(exist_ok=True)
        target=history/(p.stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        assert out.resolve().is_relative_to(ROOT.resolve()) and target.resolve().is_relative_to(ROOT.resolve())
        out.rename(target)
    out.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,str(RENDERER),str(p),'--output_dir',str(out),'--emit_pdf','--verbose']
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',env=env)
    (out/'render.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
    print(p.name,r.returncode,len(list(out.glob('page-*.png'))),flush=True)
    if r.returncode:print(r.stderr[-2500:],flush=True)
    return r.returncode
if __name__=='__main__':
    files=sorted((ROOT/'submission').glob('*.docx'))
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(run,files))
    assert not any(codes),codes
