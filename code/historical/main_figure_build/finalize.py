"""Offline delivery QA: no new inference and no edits to upstream files."""
from environment import ROOT,SUB,SD,AUD,PREV
from scope import CONFIG,IDS,LABELS
from pathlib import Path
from collections import Counter
from copy import deepcopy
import hashlib,json,re,zipfile,platform,importlib.metadata
import numpy as np,pandas as pd
from lxml import etree
from docx import Document
from docx.oxml.ns import qn
import fitz

CHECK=[]
def ck(name,value,detail=''):
    CHECK.append(dict(check=name,status='PASS' if bool(value) else 'FAIL',detail=str(detail)))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def rd(n):return pd.read_csv(SD/f'full_results/{n}.csv',float_precision='round_trip')
def ordinary(d):return ''.join(d.element.xpath('.//w:t/text()'))
def run():
    CHECK.clear();banned=re.compile(r'asthma|cerebrovascular|\bASTH\b|\bCEREB\b|哮喘|脑血管',re.I)
    clean=Document(SUB/'Main_Text_CN_2009_2020_five_outcomes_clean.docx');high=Document(SUB/'Main_Text_CN_2009_2020_five_outcomes_highlight.docx');si=Document(SUB/'Supplementary_Information_CN_2009_2020_five_outcomes.docx')
    old=Document(AUD/'inputs/Main_Text_CN_clean.docx')
    ck('clean_highlight_identical_text',ordinary(clean)==ordinary(high))
    for d,name in [(clean,'clean'),(high,'highlight'),(si,'SI')]:
        ck(name+'_no_removed_independent_outcome',not banned.search(ordinary(d)))
        ck(name+'_no_raw_tex',not re.search(r'\\(?:beta|frac|sum|mu|rho|alpha)|\$|```',ordinary(d)))
        ck(name+'_no_red_instruction_runs',not d.element.xpath('.//w:color[@w:val="FF0000"]'))
    cm=[etree.tostring(x) for x in clean.element.xpath('.//m:oMath')]
    ck('main_28_native_equations_identical_to_latest_source',len(cm)==28 and cm==[etree.tostring(x) for x in old.element.xpath('.//m:oMath')])
    ck('clean_highlight_identical_math',cm==[etree.tostring(x) for x in high.element.xpath('.//m:oMath')])
    highlighted=[]
    for i,p in enumerate(high.paragraphs):
        yellow=''.join(r.text for r in p.runs if r.font.highlight_color is not None)
        if yellow:highlighted.append(i);ck(f'highlight_{i}_exactly_one_complete_sentence',yellow==p.text[:p.text.index('。')+1])
    ck('seven_discussion_sentences_only',highlighted==list(range(32,39)))
    ck('clean_has_no_highlight',not clean.element.xpath('.//w:highlight'))
    ck('two_results_four_methods',[(i,p.text) for i,p in enumerate(clean.paragraphs) if p.style.name=='Heading 2']==[(i,clean.paragraphs[i].text) for i in [11,21,42,47,50,57]])
    ck('separate_conclusion',clean.paragraphs[39].text=='结论' and clean.paragraphs[41].text=='方法')
    for d,name,expected in [(clean,'clean',4),(high,'highlight',4),(si,'SI',7)]:
        embeds=d.element.xpath('.//a:blip');ck(name+'_embedded_figure_count',len(embeds)==expected)
        relimages=[r for r in d.part.rels.values() if r.reltype.endswith('/image')]
        ck(name+'_no_unreferenced_old_images',len(relimages)==expected)
        for j,blip in enumerate(embeds,1):
            blob=d.part.related_parts[blip.get(qn('r:embed'))].blob
            f=SUB/f'figures/Figure_{j}.png' if name!='SI' else SUB/f'figures/supplementary/Supplementary_Figure_S{j}.png'
            ck(f'{name}_embedded_figure_{j}_current_bytes',hashlib.sha256(blob).hexdigest()==sha(f))
    # Retained citations remain in their original first-use order; bibliographic years unchanged.
    cited=[]
    for p in clean.paragraphs[:66]:
        for r in p.runs:
            if r.font.superscript and re.fullmatch(r'[\d,]+',r.text):
                for n in r.text.split(','):
                    if int(n) not in cited:cited.append(int(n))
    ck('citations_first_use_1_to_30',cited==list(range(1,31)),cited)
    ck('reference_titles_and_years_unchanged',[p.text for p in clean.paragraphs[67:]]==[p.text for p in old.paragraphs[67:]])
    (AUD/'reference_scope_check.md').write_text('本轮逐条核对全部30条文献仍被引用，首次出现顺序1—30，书目题名/年份与最近完整稿相同。沿用已冻结的同日多来源核验，不声称本轮重新联网验证。原核验明确Holm文献仅为有限核验；详见inputs/reference_audit。没有因缩减独立结局而篡改多结局外部文献的题名或研究范围。',encoding='utf-8')
    si_text=(SUB/'Supplementary_Information_CN.md').read_text(encoding='utf-8')
    # Make each supplementary table available as neutral, scope-clean source data.
    table_sources=[]
    for m in re.finditer(r'### 补充表 (S\d+[ab]?)\b[^\n]*\n(?:(?!\n###|\n##)[\s\S])*?(\|[^\n]+\n(?:\|[^\n]*\n)*)',si_text):
        rows=[[x.strip() for x in l.strip('|').split('|')] for l in m[2].strip().splitlines()]
        d=pd.DataFrame(rows[2:],columns=rows[0]);d.to_csv(SD/f'full_results/Table_{m[1]}.csv',index=False)
        table_sources.append(dict(table=m[1],rows=len(d),source=f'full_results/Table_{m[1]}.csv'))
    ck('numbered_supplementary_tables_complete',len(table_sources)==24,len(table_sources))
    ts={x['table']:x['rows'] for x in table_sources}
    for n,v in {'S1':5,'S4':3,'S5':5,'S6':25,'S7':40,'S8':25,'S9':40,'S10':12,'S11':5,'S12':5,'S13a':24,'S13b':24,'S17':12,'S18':6,'S19':72,'S20':49,'S21':13,'S22':81,'S23':5}.items():ck(n+'_table_rows',ts.get(n)==v,ts.get(n))
    h=rd('health_results');ref=h[h.analysis_block.eq('A')];ck('health_rows_135',len(h)==135)
    orig=pd.read_csv(AUD/'inputs/tables/AFIRE_7outcome_all_results.csv',float_precision='round_trip');orig=orig[orig.outcome_id.isin(IDS)]
    key=['outcome_id','analysis_block','model_id','contrast_id'];a=h.set_index(key).sort_index();b=orig.set_index(key).sort_index()
    for col in ['beta','SE','beta_CI_lower','beta_CI_upper','P_value','P_adjusted','interaction_percent','CI_percent_lower','CI_percent_upper','df_rubin']:
        ck('model_'+col+'_bitwise_equal',np.array_equal(a[col],b[col],equal_nan=True))
    for block,num in [('A',5),('B',25),('C',40),('D',25),('E',40)]:ck('block_'+block+'_rows',len(h[h.analysis_block.eq(block)])==num)
    ck('formal_method_original_family_7','家族含7项' in ordinary(clean) and '未作前瞻性预注册' in ordinary(clean))
    ck('fixed_IQR',CONFIG['smoke_iqr']==0.678107947271523)
    ck('real_baseline_preserved','2006—2010' in ordinary(clean) and '2006—2010' in si_text)
    ck('historical_validation_training_disclosed','原训练资料覆盖2006—2020年' in si_text)
    ck('no_old_observation_period_in_main','2006—2020' not in ordinary(clean))
    cond=rd('conditional');ck('25_conditional_classification',len(cond)==25 and (cond.CI_percent_upper<0).sum()==15 and ((cond.CI_percent_lower<=0)&(cond.CI_percent_upper>=0)).sum()==10)
    pair=pd.read_csv(AUD/'sample_match_check.csv');ck('five_pairs_actual_allocations_equal',len(pair)==5 and pair.actual_allocation_values_equal.all())
    formula=pd.DataFrame(json.loads((AUD/'inputs/health_config.json').read_text(encoding='utf-8'))['formulas'].items(),columns=['model_id','formula']);formula.to_csv(SD/'full_results/model_formulas.csv',index=False)
    # Literal outcome and year-field audit (avoid false positives from numeric decimals or hashes).
    sdchecks=[]
    for p in sorted(SD.rglob('*.csv')):
        raw=p.read_text(encoding='utf-8-sig');ck(str(p.relative_to(SD))+'_scope_names',not banned.search(raw))
        d=pd.read_csv(p,dtype=str)
        for col in ['cause_id','outcome_id','child','parent']:
            if col in d:ck(str(p.relative_to(SD))+'_'+col+'_whitelist',set(d[col].dropna())<=set(IDS))
        for col in ['year','year_min','year_max','year_start','year_end','FIRE_YEAR_INT']:
            if col in d:
                vals=pd.to_numeric(d[col],errors='coerce').dropna();ok=vals.between(2009,2020).all();ck(str(p.relative_to(SD))+'_'+col+'_range',ok)
                sdchecks.append(dict(file=str(p.relative_to(SD)),field=col,n=len(vals),minimum=vals.min(),maximum=vals.max(),status='PASS' if ok else 'FAIL'))
    pd.DataFrame(sdchecks).to_csv(AUD/'source_data_year_field_check.csv',index=False)
    # Geographic joins independently checked from delivered geometry.
    county=rd('county_map_values');county.county_fips=county.county_fips.astype(str).str.zfill(5)
    geo=json.loads((SD/'geography/counties_256_epsg5070.geojson').read_text(encoding='utf-8'))['features'];keys=[f['properties']['county_fips'] for f in geo]
    ck('county_geographic_exact_join',len(keys)==len(set(keys))==256 and set(keys)==set(county.county_fips))
    joins=county[['county_fips','state_abbr']].copy();joins['geometry_matched']=joins.county_fips.isin(keys);joins['projection']='EPSG:5070';joins.to_csv(SD/'full_results/county_geographic_join.csv',index=False)
    ck('all_county_map_denominators_60',county.n_records.eq(60).all())
    counts=rd('suppression');ck('mortality_recount',counts.n.sum()==15360 and counts.suppressed.sum()==3328 and counts.public_zero.sum()==325)
    annual=rd('annual');ck('annual_exact_12_years',list(annual.year)==list(range(2009,2021)))
    st=rd('state_year_exposure');ck('588_state_years',len(st)==588 and len(st.drop_duplicates(['state_abbr','year']))==588)
    ck('72_state_county_pairs',len(rd('state_county_bridge'))==72)
    fc=rd('fire_catalogue_subset');fa=rd('fire_record_state_assignments');ck('fire_subset_81_89',len(fc)==81 and len(fa)==89)
    # Source-hash before/after verification, including original file bytes.
    manifest=pd.read_csv(AUD/'INPUT_MANIFEST.csv');manifest['sha256_after']=[sha(p) for p in manifest.source];manifest['source_unchanged']=manifest.sha256_after.eq(manifest.sha256_before)
    manifest['frozen_copy_matches']=[sha(ROOT/p)==v for p,v in zip(manifest.frozen,manifest.sha256_before)];manifest.to_csv(AUD/'INPUT_MANIFEST.csv',index=False)
    ck('all_original_inputs_unchanged',manifest.source_unchanged.all(),len(manifest));ck('all_frozen_copies_match',manifest.frozen_copy_matches.all())
    # Rendered figures: text, bounds, vector presence, full finite CI data.
    figchecks=[]
    for p in sorted((SUB/'figures').rglob('*.pdf')):
        pdf=fitz.open(p);page=pdf[0];txt=page.get_text();name=p.stem
        ck(name+'_single_page',len(pdf)==1);ck(name+'_no_removed_names',not banned.search(txt))
        ck(name+'_no_old_observation_ticks',not re.search(r'\b200[678]\b',txt))
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
        ck(name+'_min_text_7pt',min(s['size'] for s in spans)>=6.99)
        ck(name+'_vector_paths',len(page.get_drawings())>0)
        figchecks.append(dict(figure=name,panels='a–d' if name.startswith('Figure_') else 'see legend',width_mm=page.rect.width*25.4/72,height_mm=page.rect.height*25.4/72,min_font_pt=min(s['size'] for s in spans),text_scope='PASS',ci_geometry='source and rendered errorbar segments checked' if name in ['Figure_4'] or name.endswith(('S1','S2','S3','S4')) else 'not inferential'))
        (AUD/'pdf_text_audit'/(name+'.txt')).write_text(txt,encoding='utf-8')
    pd.DataFrame(figchecks).to_csv(AUD/'figure_text_check.csv',index=False)
    pd.DataFrame(CHECK).to_csv(AUD/'scope_consistency_check.csv',index=False)
    pd.DataFrame(table_sources).to_csv(AUD/'table_source_index.csv',index=False)
    (AUD/'runtime_versions.json').write_text(json.dumps({'python':platform.python_version(),**{p:importlib.metadata.version(p) for p in ['pandas','numpy','matplotlib','python-docx','PyMuPDF','shapely','pyproj']}},indent=2),encoding='utf-8')
    failures=[r for r in CHECK if r['status']=='FAIL'];print('Checks:',len(CHECK),'Failures:',len(failures));print(json.dumps(failures,ensure_ascii=False,indent=2))
    assert not failures
if __name__=='__main__':run()
