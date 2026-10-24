"""Patch SI references only in the actual author DOCX, preserving every other ZIP part."""
from pathlib import Path
import csv, difflib, hashlib, json, re, zipfile
from lxml import etree

OUT=Path(__file__).resolve().parents[1]
CFG=json.loads((OUT/'scripts/scope_config.yaml').read_text(encoding='utf-8'))
BASE=Path(CFG['base'])
SOURCE=BASE/'submission/Main_Text_CN_2009_2020_five_outcomes_clean.docx'
TARGET=OUT/'submission/Main_Text_CN_SI_links_synced.docx'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W='{'+NS['w']+'}'

# Literal groups are intentional: a mixed table/data range cannot be blindly renumbered.
REPLACEMENTS={
    '补充表S20—S22':'补充数据1和3及补充表7',
    '补充表S21—S22':'补充表7及补充数据3',
    '补充表S7、S9及S23':'补充表17、19及22',
    '补充表S5—S9':'补充表15—19',
    '补充表S8—S9':'补充表18—19',
    '补充表S2、S20':'补充表2及补充数据1',
    '补充表S13':'补充表9—10',
    '补充表S23':'补充表22',
    '补充表S19':'补充数据2',
    '补充表S11':'补充表6',
    '补充表S5':'补充表15',
    '补充表S6':'补充表16',
    '补充表S8':'补充表18',
    '补充表S4':'补充表12',
    '补充表S1':'补充表1',
    '补充S3':'补充方法4',
    '补充S8':'补充方法5',
}
def digest(b):return hashlib.sha256(b).hexdigest()
def text(p):return ''.join(p.xpath('.//w:t/text()',namespaces=NS))
def replace_span(p,start,end,new):
    nodes=p.xpath('.//w:t',namespaces=NS);offset=0;affected=[]
    for node in nodes:
        t=node.text or '';a=offset;b=offset+len(t);offset=b
        if b>start and a<end:affected.append((node,a,b,t))
    assert affected
    for j,(node,a,b,t) in enumerate(affected):
        left=t[:max(0,start-a)];right=t[max(0,end-a):]
        node.text=left+(new if j==0 else '')+right
        if node.text.startswith(' ') or node.text.endswith(' '):node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
def main():
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    before=SOURCE.read_bytes();source_sha=digest(before)
    with zipfile.ZipFile(SOURCE) as z:
        items={i.filename:z.read(i.filename) for i in z.infolist()};infos=z.infolist()
    root=etree.fromstring(items['word/document.xml']);paras=root.xpath('//w:body//w:p',namespaces=NS)
    before_text=[text(p) for p in paras];changes=[];crossrefs=[]
    for pi,p in enumerate(paras):
        original=text(p);matches=[]
        pattern=re.compile('|'.join(re.escape(k) for k in REPLACEMENTS))
        for m in pattern.finditer(original):
            replacement=REPLACEMENTS[m.group(0)];matches.append((m.start(),m.end(),replacement))
            crossrefs.append({'paragraph_index':pi,'before':m.group(0),'after':replacement,'status':'PASS','target_status':'defined_in_scope_config'})
        for a,b,n in reversed(matches):replace_span(p,a,b,n)
        expected=pattern.sub(lambda m:REPLACEMENTS[m.group(0)],original)
        assert text(p)==expected,(pi,text(p),expected)
        if text(p)!=original:changes.append({'paragraph_index':pi,'before':original,'after':text(p),'reason':'SI reference renumbering only; table-to-data moves explicit'})
    after_text=[text(p) for p in paras]
    assert not re.search(r'补充(?:表|图)?S\d','\n'.join(after_text))
    assert all('补充数据'+str(i) in '\n'.join(after_text) for i in [1,2,3])
    replacement=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    with zipfile.ZipFile(TARGET,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for info in infos:z.writestr(info,replacement if info.filename=='word/document.xml' else items[info.filename])
    with zipfile.ZipFile(TARGET) as z:
        unchanged=[name for name,data in items.items() if name!='word/document.xml' and z.read(name)==data]
        assert len(unchanged)==len(items)-1
        newroot=etree.fromstring(z.read('word/document.xml'))
    for query in ['//m:oMath','//w:drawing','//w:commentReference','//w:ins','//w:del']:
        oldroot=etree.fromstring(items['word/document.xml'])
        assert [etree.tostring(x,method='c14n') for x in oldroot.xpath(query,namespaces=NS)]==[etree.tostring(x,method='c14n') for x in newroot.xpath(query,namespaces=NS)]
    assert digest(SOURCE.read_bytes())==source_sha
    audit=OUT/'audit';audit.mkdir(exist_ok=True)
    (audit/'maintext_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
    with (audit/'maintext_si_crossrefs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(crossrefs[0]));w.writeheader();w.writerows(crossrefs)
    diff='\n'.join(difflib.unified_diff(before_text,after_text,fromfile=SOURCE.name,tofile=TARGET.name,lineterm=''))
    (audit/'maintext_si_only.diff').write_text(diff,encoding='utf-8')
    report=f'''# 正文最小补充引用同步\n\n采用实际作者 clean 稿：`{SOURCE}`\n\n源 SHA256：{source_sha}\n\n输出：`{TARGET}`\n\n仅修改 {len(changes)} 个段落内的 {len(crossrefs)} 处补充引用。旧表 S13 明确展开为补充表9—10；旧 S20、S19、S22 分别迁为补充数据1、2、3，三份附件均保留正文入口。原两 Results、四主图、式1—3、作者正文修改和括号编辑提示均未改。\n\n所有 {len(unchanged)} 个非 document.xml ZIP 部件逐字节相同；原生公式、主图嵌入、批注和修订XML均比较一致。源文件未改。逐项变更见 maintext_changes.json、maintext_si_only.diff 与 maintext_si_crossrefs.csv。\n\n视觉核验由主构建流程对最终副本重新渲染后记录；此脚本不冒称渲染通过。\n'''
    (audit/'maintext_changes.md').write_text(report,encoding='utf-8')
    (audit/'maintext_sync_integrity.json').write_text(json.dumps({'source':str(SOURCE),'source_sha256':source_sha,'output':str(TARGET),'output_sha256':digest(TARGET.read_bytes()),'changed_paragraphs':len(changes),'changed_references':len(crossrefs),'unchanged_package_parts':len(unchanged),'source_unchanged':True,'all_other_paragraph_text_unchanged':True,'equations_and_figures_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
    print(report)
if __name__=='__main__':main()
