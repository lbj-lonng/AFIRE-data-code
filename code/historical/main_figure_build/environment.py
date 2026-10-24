"""Local scope-revision environment; no global settings are changed."""
import os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SUB=ROOT/'submission'; AUD=ROOT/'audit'; SD=SUB/'source_data'
PREV=ROOT.parent/'AFIRE_manuscript_figures_integrated_20260915_170300'
sys.dont_write_bytecode=True
for p in [SUB,SD,AUD,AUD/'inputs',AUD/'tmp',AUD/'mpl',AUD/'pdf_text_audit',AUD/'skill_validation',SUB/'figures',SUB/'figures/supplementary']:
    p.mkdir(parents=True,exist_ok=True)
for k in ['TEMP','TMP','TMPDIR']:os.environ[k]=str(AUD/'tmp')
os.environ['MPLCONFIGDIR']=str(AUD/'mpl')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['PYTHONIOENCODING']='utf-8'
sys.path.extend([str(ROOT/'scripts/qa_helpers'),'C:/Users/86189/Documents/Codex/2026-09-10/ban/work/pydeps',str(ROOT.parents[1]/'AFIRE_threepart_mainfig_redesign_20260912_173900/_work/deps'),str(PREV/'_work/mathdeps')])
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
