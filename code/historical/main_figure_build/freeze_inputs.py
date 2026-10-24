"""One-time local input snapshot. This script never fits or imputes anything."""
from environment import ROOT,PREV,AUD,SD
from pathlib import Path
import shutil,hashlib,json,csv
BASE=ROOT.parents[1]
records=[]
def freeze(src,relative):
    src=Path(src);out=ROOT/relative
    if src.is_dir():
        for p in src.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:freeze(p,str(Path(relative)/p.relative_to(src)))
        return
    before=hashlib.sha256(src.read_bytes()).hexdigest()
    out.parent.mkdir(parents=True,exist_ok=True)
    if not out.exists():shutil.copy2(src,out)
    assert hashlib.sha256(out.read_bytes()).hexdigest()==before,(src,out)
    records.append(dict(source=str(src),frozen=str(out.relative_to(ROOT)),sha256_before=before,bytes=src.stat().st_size))
freeze(PREV/'02_source_data/full_results','audit/inputs/tables')
freeze(PREV/'02_source_data/Figure_1','audit/inputs/state_panels')
freeze(PREV/'02_source_data/geography','submission/source_data/geography')
freeze(PREV/'05_manuscripts/Main_Text_CN_clean.docx','audit/inputs/Main_Text_CN_clean.docx')
freeze(PREV/'05_manuscripts/Main_Text_CN_discussion_highlight.docx','audit/inputs/Main_Text_CN_discussion_highlight.docx')
freeze(PREV/'06_supplementary/Supplementary_Information_CN.docx','audit/inputs/Supplementary_Information_CN.docx')
freeze(PREV/'06_supplementary/Supplementary_Information_CN.md','audit/inputs/Supplementary_Information_CN.md')
freeze(PREV/'06_supplementary/equations.tex','audit/inputs/previous_equations.tex')
freeze(PREV/'00_control/reference_audit','audit/inputs/reference_audit')
freeze(PREV/'00_control/health_pair_audit','audit/inputs/previous_pair_audit')
freeze(PREV/'08_delivery','audit/inputs/previous_delivery')
freeze(PREV/'00_control/skill_read_ledger.csv','audit/inputs/previous_skill_reads.csv')
freeze(BASE/'paper_package_verified_20260908/paper_package_verified_20260908/data/result2/pseudo_suppression_predictions.csv','audit/inputs/validation_predictions.csv')
freeze(BASE/'paper_package_verified_20260908/paper_package_verified_20260908/data/analysis/county_year_disease_panel_v6_3.csv','audit/inputs/mortality_panel.csv')
auth=BASE/'AFIRE_7outcome_extension_20260911_234642_lTDb'
freeze(auth/'config.json','audit/inputs/health_config.json')
for cause in ['copd','chronic_lower_respiratory','respiratory_system','circulatory_system','ischemic_heart_disease']:
    for tag in ['A__reference','C__M2','C__M3PL_joint']:
        freeze(auth/f'sample_keys/{cause}__{tag}.csv',f'audit/inputs/sample_keys/{cause}__{tag}.csv')
        freeze(auth/f'per_imputation/{cause}__{tag}.csv',f'audit/inputs/per_imputation/{cause}__{tag}.csv')
for name in ['shared_style.py','plot_figure_1.py','plot_figure_2.py','plot_figure_3.py','plot_figure_4.py','render_docx_local.py','render_documents.py','build_supplement.py']:
    freeze(PREV/'03_scripts'/name,'audit/inputs/previous_scripts/'+name)
    if name.startswith('plot_') or name=='shared_style.py':
        dest=ROOT/'scripts'/name
        if not dest.exists():shutil.copy2(PREV/'03_scripts'/name,dest)
for name in ['validate_figure.py','audit_pdf_text.py','audit_panel_alignment.py','audit_figure_collisions.py']:
    freeze(Path('C:/Users/86189/.codex/skills/nature-figure/scripts')/name,'scripts/qa_helpers/'+name)
with (AUD/'INPUT_MANIFEST.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
print('Frozen inputs:',len(records))
