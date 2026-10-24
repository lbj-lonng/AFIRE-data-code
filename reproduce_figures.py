"""Stage frozen inputs and run archived plotting code without modifying the release."""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True,help='NEW output directory; existing directories are refused')
    ap.add_argument('--figures',choices=['main','supplement','extra','all'],default='all')
    a=ap.parse_args();repo=Path(__file__).resolve().parent;out=a.output.resolve()
    if out.exists():raise SystemExit('Choose a new output directory; existing outputs are never overwritten.')
    if repo==out or repo in out.parents and 'outputs' not in out.relative_to(repo).parts:
        raise SystemExit('Use a directory outside the release or under its ignored outputs/ directory.')
    out.mkdir(parents=True)
    mainroot=out/'AFIRE_2009_2020_five_outcomes_20260915_194616'
    siroot=out/'AFIRE_Supplement_integrated_20260916_230522'
    extra=out/'S8_S10'
    def stage(src,dst):shutil.copytree(src,dst,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    stage(repo/'data/source_data',mainroot/'submission/source_data')
    stage(repo/'code/historical/main_figure_build',mainroot/'scripts')
    env='''import os,sys\nfrom pathlib import Path\nROOT=Path(__file__).resolve().parents[1]\nSUB=ROOT/'submission';SD=SUB/'source_data';AUD=ROOT/'audit'\nPREV=ROOT\nfor p in [SUB,SD,AUD,AUD/'tmp',AUD/'mpl',AUD/'pdf_text_audit',SUB/'figures']:\n p.mkdir(parents=True,exist_ok=True)\nos.environ['MPLCONFIGDIR']=str(AUD/'mpl')\nsys.path.insert(0,str(ROOT/'scripts/qa_helpers'))\n'''
    (mainroot/'scripts/environment.py').write_text(env,encoding='utf-8')
    stage(repo/'code/historical/supplement_build',siroot/'scripts')
    stage(repo/'data/source_data',siroot/'submission/source_data')
    stage(repo/'code/historical/S8_S10_build',extra/'scripts')
    # Change only a temporary staged copy. Original code snapshots remain byte-identical.
    ep=extra/'scripts/build_visual_extension.py';text=ep.read_text(encoding='utf-8')
    text=re.sub(r'^BASE = Path\(.*$',"BASE = ROOT.parent / 'AFIRE_Supplement_integrated_20260916_230522'",text,flags=re.M)
    ep.write_text(text,encoding='utf-8')
    # Remove obsolete machine-specific import paths in staged scripts.
    for folder in [mainroot/'scripts',siroot/'scripts',extra/'scripts']:
        for p in folder.rglob('*.py'):
            s=p.read_text(encoding='utf-8-sig')
            s=re.sub(r'^sys\.path\.insert\(0, r[\x27\x22][CD]:[^\n]+\n','',s,flags=re.M)
            p.write_text(s,encoding='utf-8')
    jobs=[]
    if a.figures in ['main','all']:jobs += [mainroot/'scripts'/f'plot_figure_{n}.py' for n in range(1,5)]
    if a.figures in ['supplement','all']:jobs.append(siroot/'scripts/plot_supplement.py')
    if a.figures in ['extra','all']:jobs.append(ep)
    history=[]
    for p in jobs:
        print('Rebuilding',p.name,flush=True)
        result=subprocess.run([sys.executable,'-X','utf8',str(p)],capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        (out/(p.stem+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        history.append({'script':p.name,'returncode':result.returncode})
        if result.returncode:print(result.stderr[-2500:]);break
    (out/'reproduction_status.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
    if any(x['returncode'] for x in history):raise SystemExit(1)
    print('Plotting completed. Saved estimates were not refitted. Review regenerated layouts before submission.')
if __name__=='__main__':main()
