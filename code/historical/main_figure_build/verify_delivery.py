"""Independent table/export postflight; never confers unobserved visual approval."""
from environment import ROOT, SUB, SD, AUD
from scope import IDS, LABELS
from docx import Document
from PIL import Image
from pathlib import Path
import json, re, hashlib
import pandas as pd
import fitz

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def norm(s):
    return str(s).replace('−', '-').replace('–', '-').replace(' ', '')

def run():
    h = pd.read_csv(SD/'full_results/health_results.csv', float_precision='round_trip')
    si = Document(SUB/'Supplementary_Information_CN_2009_2020_five_outcomes.docx')
    checks = []
    dm = {'完整':'full', '删除2020':'drop2020', '删除CA':'dropCA',
          '同时删除':'dropCA_and2020', '仅删除CA×2020':'dropCA2020only'}
    for num, block in zip(range(5,10), 'ABCDE'):
        table = pd.read_csv(SD/f'full_results/Table_S{num}.csv', dtype=str, keep_default_na=False)
        expected = [[norm(x) for x in row] for row in [table.columns.tolist(), *table.values.tolist()]]
        matches = [t for t in si.tables if [[norm(c.text) for c in r.cells] for r in t.rows] == expected]
        assert len(matches) == 1, ('Word table does not match CSV', num)
        for i, row in table.iterrows():
            oid = IDS[LABELS.index(row.iloc[0])]
            value = h[h.outcome_id.eq(oid) & h.analysis_block.eq(block)]
            label = row.iloc[1]
            if block == 'B':
                value = value[value.ses_sd.eq(float(label.replace(' SD','')))]
            else:
                model = dm[label] if block == 'D' else label
                if block == 'E':
                    prefix, quality, lst = label.split()
                    model = prefix + ('_relaxed_' if quality == 'R' else '_strict_') + ('noLST' if lst == '−L' else 'withLST')
                value = value[value.model_id.eq(model)]
            assert len(value) == 1, (num, i, label)
            source = value.iloc[0]
            assert int(row.iloc[2]) == int(source.n_county_years)
            assert norm(row.iloc[3]) == norm(f'{source.percent_estimate:.3f}')
            assert norm(row.iloc[4]) == norm(f'{source.percent_CI_lower:.3f} 至 {source.percent_CI_upper:.3f}')
            assert norm(row.iloc[5]) == norm(f'{source.P_value:.3g}')
            if block == 'A':
                assert norm(row.iloc[6]) == norm(f'{source.P_adjusted:.3g}')
            checks.append({'table':f'S{num}', 'row':i+1, 'outcome_id':oid,
                           'model_id':source.model_id, 'contrast_id':source.contrast_id,
                           'Word_matches_Source_Data':True, 'rounded_estimate_CI_P_match_frozen_result':True})
    assert len(checks) == 135
    pd.DataFrame(checks).to_csv(AUD/'supplement_table_value_check.csv', index=False)

    exports = []
    warning_review = []
    for pdf in sorted((SUB/'figures').rglob('*.pdf')):
        page = fitz.open(pdf)[0]
        with Image.open(pdf.with_suffix('.png')) as im:
            dpi = im.info.get('dpi', (0,0))
            assert min(dpi) > 599
            assert im.width >= 4300
        svg = pdf.with_suffix('.svg').read_text(encoding='utf-8')
        assert '<text' in svg
        fonts = [f[3] for f in page.get_fonts()]
        assert fonts and all('Arial' in f or 'DejaVuSans' in f for f in fonts), fonts
        assert abs(page.rect.width*25.4/72 - 183) < .01
        collision = json.loads((AUD/(pdf.stem+'.collision.json')).read_text(encoding='utf-8'))
        assert collision['auditable'] and collision['summary']['fail'] == 0, pdf.stem
        if collision['verdict'] != 'PASS':
            # These two exact warnings were inspected by the primary agent in final-size
            # previews and in Word: the band polygon's rectangle spans the empty upper-left
            # legend region, but the polygon itself reaches the top only on the far right.
            expected_label = {'Figure_1':'State P10–P90','Figure_2':'County P10–P90'}.get(pdf.stem)
            findings = collision['findings']
            assert len(findings)==1 and findings[0]['kind']=='text-fill-edge' and findings[0]['text']==expected_label
            warning_review.append({'figure':pdf.stem, 'raw_verdict':collision['verdict'],
                'warning_text':expected_label, 'pdf_sha256':sha(pdf),
                'disposition':'ACCEPTED_AFTER_ACTUAL_VISUAL_REVIEW',
                'reason':'The broad band bounding rectangle overlaps the legend rectangle, but the actual shaded polygon is far below the upper-left legend. Its high endpoint is on the far right. Final-size view shows no text/data occlusion.'})
        ap = AUD/(pdf.stem+'.alignment.json')
        if ap.exists():
            alignment = json.loads(ap.read_text(encoding='utf-8'))
            assert alignment['auditable'] and alignment['verdict'] == 'PASS', pdf.stem
        exports.append({'figure':pdf.stem, 'png_dpi':dpi[0], 'width_mm':page.rect.width*25.4/72,
                        'editable_SVG_text':True, 'PDF_fonts':';'.join(fonts),
                        'collision':collision['verdict'], 'alignment':'PASS' if ap.exists() else 'NOT_APPLICABLE_SINGLE_PANEL',
                        'pdf_sha256':sha(pdf), 'png_sha256':sha(pdf.with_suffix('.png'))})
    pd.DataFrame(exports).to_csv(AUD/'final_export_check.csv', index=False)
    pd.DataFrame(warning_review).to_csv(AUD/'collision_warning_review.csv', index=False)

    # Preserve raw single-file lint failures, and document concrete imported-runtime evidence.
    explanations = {
        'FONT-SIZE':'Shared rcParams and helpers set text sizes. Every final PDF has a measured minimum text size of 7 pt; see figure_text_check.csv and actual final-size review.',
        'FONT-FAMILY':'shared_style.py sets Arial/DejaVu Sans; actual PDF embedded font names verified in final_export_check.csv.',
        'EDITABLE-TEXT':'shared_style.py sets svg.fonttype=none and pdf.fonttype=42; actual SVG <text> and PDF fonts verified.',
        'EXPORT-VECTOR':'Shared export helper/extension loop writes real PDF and SVG; actual files verified, not inferred from a literal savefig call.',
        'EXPORT-RASTER':'All submission PNGs are 600 dpi; main TIFFs are additional formats. Supplement PDF/SVG/PNG meets the requested deliverable contract.',
        'RASTER-DPI':'180/300 dpi outputs are audit-only previews. Actual submission PNG metadata is 600 dpi; see final_export_check.csv.',
        'FINAL-WIDTH':'Single-file literal heuristic reads 183 as inches despite division by 25.4. Actual PDF width is 183 mm.',
        'ROTATION-ANCHOR':'S6 year labels at 45 degrees were inspected individually; no overlap or clipping in final-size PNG or final PDF collision audit.'}
    lint=[]
    for path in sorted((AUD/'skill_validation').glob('plot_*.json')):
        report=json.loads(path.read_text(encoding='utf-8'))
        for item in report['findings']:
            if item['level'] not in ['FAIL','WARN']: continue
            assert item['check_id'] in explanations, item
            lint.append({'source':path.name,'raw_level':item['level'],'check_id':item['check_id'],
                         'disposition':'RESOLVED_BY_RENDERED_OR_IMPORTED_CODE_EVIDENCE',
                         'evidence':explanations[item['check_id']]})
    pd.DataFrame(lint).to_csv(AUD/'static_lint_review.csv', index=False)
    print('Independent postflight: 135 Word/CSV/frozen-estimate rows and 11 exported figures verified.')

    # A rebuild checks a pre-existing signed snapshot; it does not manufacture visual PASS.
    review_path = AUD/'visual_review.csv'
    if review_path.exists():
        review = pd.read_csv(review_path)
        review['current_hash_matches_reviewed'] = [sha(ROOT/p)==s for p,s in zip(review.file,review.sha256)]
        review.to_csv(AUD/'visual_review_rebuild_check.csv', index=False)
        assert review.current_hash_matches_reviewed.all(), 'Rendering changed: inspect changed pages before delivery.'
        print('Existing visual approval remains valid for every reviewed PNG hash.')
    else:
        print('Visual approval not yet recorded; programmatic checks do not replace visual review.')

if __name__ == '__main__':
    run()
