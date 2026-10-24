"""Curated history migration and author-edit audit; never edits historical artifacts."""
from pathlib import Path
from lxml import etree
from datetime import datetime
import csv,difflib,hashlib,io,json,re,zipfile
from pypdf import PdfReader

ROOT=Path(r'D:\postgraduate\wildfire\9.10')
OUT=ROOT/'9.15/AFIRE_Supplement_integrated_20260916_230522'
BASE=ROOT/'9.15/AFIRE_2009_2020_five_outcomes_20260915_194616'
AUD=OUT/'audit'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
CFG=json.loads((OUT/'scripts/scope_config.yaml').read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def writecsv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def doctext(p):
    with zipfile.ZipFile(p) as z:
        root=etree.fromstring(z.read('word/document.xml'))
        return [''.join(p.xpath('.//w:t/text() | .//m:t/text()',namespaces=NS)) for p in root.xpath('//w:body/w:p',namespaces=NS)]
def target_for(heading,body,latest=False):
    # Hierarchy-first classification, with final destinations frozen in the root scope configuration.
    t=re.search(r'补充表\s*(S\d+[ab]?)',heading)
    f=re.search(r'补充图\s*(S\d+)',heading)
    s=re.match(r'##\s+(S\d+)\b',heading)
    if t and latest:
        x=t.group(1)
        if x in CFG['table_map']:return '保留','Supplementary Table '+str(CFG['table_map'][x]),'最新范围数值保留；主题重排并连续编号'
        if x in CFG['data_map']:return '保留','Supplementary Data '+str(CFG['data_map'][x]),'逐行大型资料迁数据附件，正文和SI均保留明确入口'
    if f and latest:return '保留','Supplementary Fig. '+str(CFG['figure_map'][f.group(1)]),'从冻结数据重绘或优化，只改变组织和显示'
    if s and latest:return '合并去重',CFG['section_map'].get(s.group(1),'Supplementary Methods and Notes'),'按科学主题合并散落定义，保留独有事实和限制'
    if 'Equation' in heading or re.search(r'^(?:县c|州s|人口加权Gini|按社会经济劣势排序|设第m|插补内方差|总方差|主模型O10|给定SES|其线性|O03将)',heading):
        if 'Gini' in heading or '集中指数' in heading:return '纠正','Supplementary Methods 2','仅保留当前县等权Gini；旧全国人口权重和集中趋势不再成立为当前证据'
        return '纠正','Supplementary Equations 1–12','以冻结B1/扩展引擎为权威，旧FMI/离散度/小样本修正不得复流'
    if any(x in heading for x in ['优先级','脆弱性特征','脆弱性模式','代表性县','社会经济特征与','筛查']):return '范围外','audit only','旧筛查分数混合当前取消结局且估计目标不同，不恢复额外研究点'
    if any(x in heading for x in ['全国','州尺度补充','州际不平等']):return '纠正','Supplementary Methods 2; Note 1','旧人口权重存在未闭合倍数差异；改用已验证州等权分布及六州人口加权描述'
    if any(x in heading for x in ['重建','压制','抑制','缺失数据']):return '纠正','Supplementary Methods 4–5; Notes 3–4; Tables 8–13','区分已淘汰0–9主分配、当前1–9主分配与0–19验证，按五结局观察范围保留'
    if any(x in heading for x in ['验证','层级']):return '纠正','Supplementary Methods 5; Note 3; Tables 9–11','评价固定到298组2128单元，旧全范围bootstrap不移用；保留单结局层级局限'
    if any(x in heading for x in ['离散','不确定性','模型','推断','交互','边际','敏感','定向','分层','次要结局','完整结果']):return '合并去重','Supplementary Methods 6–7; Notes 5–6; Tables 14–22','当前A–E白名单135行是权威；早期不同分配估计只内部追溯，已认证B1额外COPD模型单列'
    if any(x in heading for x in ['单位','单元','来源','资料','字典','数据连接','协变量','变量','指标','基线','SES']):return '合并去重','Supplementary Methods 1–3; Tables 1–2','保留有实现和来源支持的定义；不能由历史文稿补造复合指数构成'
    if any(x in heading for x in ['暴露','地图','地理','州至县','经济背景','火灾']):return '纠正','Supplementary Methods 2–3; Notes 1–2; Tables 3–7; Data 1–3','保留2009–2020描述定义，火灾目录保持记录/州归属区别，不认证独立事件全国排名'
    if any(x in heading for x in ['参考','来源','reference']):return '纠正','Supplementary References','补充参考文献独立从1编号并按实际使用核验，不照搬历史编号'
    if any(x in heading for x in ['发布','复现','质量','版本','范围','环境','图件复现']):return '仅内部追溯','audit; scripts; Supplementary Discussion (scientific limitations only)','执行日志哈希路径进入audit；只把真正影响解释的限制保留在学术SI'
    if '补充图' in heading:return '合并去重','Supplementary Figures 1–7 or audit only','由图注科学目的决定；不恢复旧图数量，重合主体归并到当前图'
    if '补充表' in heading:return '合并去重','Supplementary Tables 1–22 or Data 1–3','旧表数值不能覆盖当前冻结身份，独有辅助主题在对应Note核对'
    return '合并去重','Supplementary Methods 1–7; Notes 1–6','结合上下文归入当前两问题证据链；不机械拼接版本历史'

def main():
    manifest=list(csv.DictReader((AUD/'history_source_manifest.csv').open(encoding='utf-8-sig')))
    manifest=[r for r in manifest if not any(x in Path(r['path']).parts for x in ['_work','node_modules','site-packages','__pycache__'])]
    current=BASE/'submission/Main_Text_CN_2009_2020_five_outcomes_clean.docx'
    high=BASE/'submission/Main_Text_CN_2009_2020_five_outcomes_highlight.docx'
    clean=doctext(current);highlight=doctext(high)
    (AUD/'author_current_vs_highlight.diff').write_text('\n'.join(difflib.unified_diff(highlight,clean,fromfile=high.name,tofile=current.name,lineterm='')),encoding='utf-8')
    oldpdf=BASE/'audit/rendered_pages/Main_Text_CN_2009_2020_five_outcomes_clean/Main_Text_CN_2009_2020_five_outcomes_clean.pdf'
    pdftxt='\n'.join(p.extract_text() or '' for p in PdfReader(oldpdf).pages)
    (AUD/'history_text/previous_generated_clean_pdf.txt').write_text(pdftxt,encoding='utf-8')
    compact=lambda x:re.sub(r'\s+','',x)
    previous=compact(pdftxt)
    change_reasons=[]
    for i,p in enumerate(clean):
        if compact(p) not in previous and (re.search('（[^）]*(?:[？?]|写|改进|优化|说明|因经济|不公平|为什么|证据)',p) or i==0):
            change_reasons.append({'paragraph':i,'author_current':p,'present_verbatim_in_previous_render':False,'action':'保留作者文字；核心结论或编辑提示待作者确认'})
    (AUD/'author_actual_changes.json').write_text(json.dumps(change_reasons,ensure_ascii=False,indent=2),encoding='utf-8')
    oldmanifest=list(csv.DictReader((BASE/'audit/DELIVERY_MANIFEST.csv').open(encoding='utf-8-sig')))
    sourceidentity=[]
    for p in [current,high,BASE/'submission/Supplementary_Information_CN_2009_2020_five_outcomes.docx']:
        old=next((r for r in oldmanifest if r['file']==p.relative_to(BASE).as_posix()),{})
        sourceidentity.append({'path':str(p),'sha256_current':sha(p),'sha256_previous_delivery':old.get('sha256',''),'matches_previous_delivery':sha(p)==old.get('sha256'),'modified_local':datetime.fromtimestamp(p.stat().st_mtime).isoformat(),'chosen':p==current})
    writecsv(AUD/'author_manuscript_identity.csv',sourceidentity)
    # Verify ZIP members against actual legacy copies; extract unique manuscript only into OUT.
    archive=ROOT/'Afire_paper_handoff_20260825.zip';archive_rows=[]
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if 'Supplementary' not in info.filename or not info.filename.endswith('.docx'):continue
            b=z.read(info.filename);h=hashlib.sha256(b).hexdigest();match=next((r['path'] for r in manifest if r['sha256']==h),'')
            extracted=''
            if not match:
                dest=(AUD/'history_archives'/Path(info.filename).name).resolve()
                assert dest.is_relative_to(OUT.resolve())
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b);extracted=str(dest)
            archive_rows.append({'archive':str(archive),'member':info.filename,'member_sha256':h,'matching_existing_copy':match,'extracted_to':extracted,'decision':'合并去重' if match else '检查独有内容'})
    writecsv(AUD/'historical_archive_member_identity.csv',archive_rows)
    legacy_cn=ROOT/'paper_package_verified_20260908/paper_package_verified_20260908/manuscript_reference/Afire_Nature_Supplementary_CN_final_v2.docx'
    for r in archive_rows:
        if r['extracted_to']:
            p=Path(r['extracted_to'])
            (AUD/'history_text/handoff_source_vs_final.diff').write_text('\n'.join(difflib.unified_diff(doctext(p),doctext(legacy_cn),fromfile=p.name,tofile=legacy_cn.name,lineterm='')),encoding='utf-8')
    # Every historical manuscript section/caption/formula gets a row, not merely each version.
    candidates=[]
    for r in manifest:
        p=Path(r['path'])
        if p.suffix=='.md' and ('Supplement' in p.name or 'supplement' in p.name):candidates.append(p)
    candidates += [ROOT/'AFIRE_Supplementary_Methods_CN.docx',ROOT/'paper_package_verified_20260908/paper_package_verified_20260908/manuscript_reference/Afire_Nature_Supplementary_CN_final_v2.docx']
    for r in archive_rows:
        if r['extracted_to']:candidates.append(Path(r['extracted_to']))
    migration=[];seen={}
    for p in sorted(set(candidates)):
        if 'EN' in p.name:continue # English companions independently inventoried, numeric topics paired with CN.
        lines=p.read_text(encoding='utf-8-sig').splitlines() if p.suffix=='.md' else doctext(p)
        marks=[i for i,l in enumerate(lines) if re.match(r'^(#{2,3}\s|Equation\s*\(|\d+\.\s|S\d+\.\s|补充[图表]\s*\d+\s*[|｜]|(?:县c|州s|人口加权Gini|按社会经济劣势排序|设第m|插补内方差|总方差|主模型O10|给定SES|其线性|O03将))',l)]
        if p.name=='AFIRE_Supplementary_Methods_CN.docx':marks=[i for i in range(2,len(lines)) if len(lines[i])<40]
        for pos,i in enumerate(marks):
            end=marks[pos+1] if pos+1<len(marks) else len(lines)
            heading=lines[i];body='\n'.join(lines[i:end]);ch=hashlib.sha256(body.encode()).hexdigest()
            latest=p.is_relative_to(BASE)
            decision,dest,reason=target_for(heading,body,latest)
            duplicate=seen.get(ch,'')
            if duplicate:decision='合并去重';reason='内容逐字相同于 '+duplicate+'；不计为独立证据。'+reason
            seen.setdefault(ch,str(p)+':'+str(i+1))
            migration.append({'old_version':p.parts[-3] if not latest else BASE.name,'source_path':str(p),'source_location':('line ' if p.suffix=='.md' else 'paragraph ')+str(i+1),'topic':heading,'current_results_or_figure':'Results 1 / Figures 1–2' if any(x in heading for x in ['暴露','州尺度','州至县','火灾','地理']) else 'Results 2 / Figures 3–4','evidence_source':'冻结A–E健康源表/原数组/原方法实现；历史版本仅定位，须按当前范围裁定','already_covered':'是，保留或纠正' if latest else '部分或后续版本覆盖','decision':decision,'destination':dest,'reason':reason,'source_sha256':sha(p),'content_sha256':ch,'duplicate_content_of':duplicate})
    # Explicit unique retired themes and known conflicting formulas, retaining auditable decisions.
    extras=[
      ('旧主分配0–9与种子20260728','纠正','Methods 4','当前正式支持1–9与已存30份；旧版本仅内部追溯'),
      ('旧Barnard–Rubin小样本修正','纠正','Methods 6','冻结引擎为传统Rubin，不引入未执行自由度方法'),
      ('旧FMI=(1+1/M)B/T','纠正','Methods 6 / final FMI equation','改用实际引擎(r+2/(nu+3))/(r+1)，不是更改数据'),
      ('旧离散度分子减拟合均值','纠正','Methods 6 / final dispersion equation','实际分子减平均完整响应；保留clip范围和条件局限'),
      ('旧FDR与事先预注册叙述','纠正','Methods 6; Discussion','沿用原七项参考交互Holm，未预注册；当前五项范围是报告选择'),
      ('全国人口加权增长倍数及趋势','仅内部追溯','audit','历史人口字段倍数异常未闭合，不用新标签恢复旧全国结论'),
      ('旧全时期495组3302单元与bootstrap区间','纠正','Tables 9–10','当前298组2128单元四法相同；当前范围无新bootstrap'),
      ('COPD旧0–9模型O01–O12/F01–F07及逐州逐年旧估计','仅内部追溯','audit','B1更新后不得混用旧分配；已有B1身份的辅助模型单列Table21'),
      ('COPD层级90份1–9既有敏感性','保留','Table 11; Note 3','单结局历史辅助证据，不是五结局联合验证或等效证明'),
      ('48县综合筛查及9项社会经济COPD相关','范围外','audit','与当前两研究问题及冻结版本不一致；不重构含取消结局的混合指标'),
      ('县贫困到州人口加权代理来源','保留','Methods 3; Note 2; Data 1','本地NHGIS字典与州聚合实现可闭合；不冒充官方州比例或县复合指标'),
      ('火灾目录97/66/100与独立事件混淆','纠正','Table 7; Data 3','当前81记录89州归属、六州55归属53不同记录；保留AK与潜在重复'),
      ('县综合劣势完整组成/方向/缺失规则','待证据','Methods 1 and author action list','字典仅给每时期标准化指标均值；无确切纳入集及上游合成实现'),
    ]
    ref=ROOT/'AFIRE_Supplementary_Methods_CN.docx'
    for theme,decision,dest,reason in extras:
        migration.append({'old_version':'cross-version conflict ledger','source_path':str(ref),'source_location':'cross-read historical methods and frozen implementations','topic':theme,'current_results_or_figure':'Methods / Results 1–2','evidence_source':'see history_integration_findings.md and source manifests','already_covered':'是或已标明未闭合','decision':decision,'destination':dest,'reason':reason,'source_sha256':sha(ref),'content_sha256':'','duplicate_content_of':''})
    writecsv(AUD/'version_content_migration.csv',migration)
    writecsv(AUD/'history_source_manifest.csv',manifest)
    print(json.dumps({'historical_sources':len(manifest),'migration_rows':len(migration),'archive_manuscripts':len(archive_rows),'author_edit_paragraphs':len(change_reasons),'baseline_identity':sourceidentity},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
