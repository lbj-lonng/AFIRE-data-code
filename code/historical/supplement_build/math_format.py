"""Native Office Math helpers mechanically reused; all imports point to this new version."""
from environment import ROOT,SUB,SD,AUD
from pathlib import Path
import hashlib,json,re,sys,zipfile
from latex2mathml.converter import convert as latex_to_mathml
from mathml2omml import convert as mathml_to_omml
from lxml import etree
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from PIL import Image
MM_NS='http://schemas.openxmlformats.org/officeDocument/2006/math'
W_NS='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
OUT=SUB;QC=AUD
INPUTS={};TABLE_RECORD=[];MATH_RECORD=[];FIGURE_RECORD=[]
def track(path):
    path=Path(path);INPUTS[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return path


def math_element(latex):
    try: mathml=latex_to_mathml(latex)
    except Exception:
        print('FAILED_LATEX',repr(latex),flush=True)
        raise
    xml=mathml_to_omml(mathml)
    # mathml2omml emits a wrong closing tag for the properties of overbars.
    # Repair only that observed malformed tag, never alter the equation tokens.
    xml=re.sub(r'(<m:groupChrPr>.*?)</m:groupChr>',r'\1</m:groupChrPr>',xml)
    if 'xmlns:m=' not in xml:
        xml=xml.replace('<m:oMath',f'<m:oMath xmlns:m="{MM_NS}" xmlns:w="{W_NS}"',1)
    try:
        node=etree.fromstring(xml.encode())
    except etree.XMLSyntaxError:
        print('FAILED_MATH',latex,xml,flush=True)
        raise
    # Hide absent sum/product limits so LibreOffice does not paint empty boxes.
    for nary in node.findall('.//{%s}nary'%MM_NS):
        pr=nary.find('{%s}naryPr'%MM_NS)
        if pr is None:pr=etree.SubElement(nary,'{%s}naryPr'%MM_NS)
        for tag in ['sub','sup']:
            slot=nary.find('{%s}%s'%(MM_NS,tag))
            if slot is None or not ''.join(slot.itertext()).strip():
                hide=etree.SubElement(pr,'{%s}%sHide'%(MM_NS,tag));hide.set('{%s}val'%MM_NS,'1')
    for group in list(node.findall('.//{%s}groupChr'%MM_NS)):
        chr_el=group.find('{%s}groupChrPr/{%s}chr'%(MM_NS,MM_NS))
        if chr_el is not None and chr_el.get('{%s}val'%MM_NS)=='¯':
            bar=etree.Element('{%s}bar'%MM_NS);pr=etree.SubElement(bar,'{%s}barPr'%MM_NS)
            pos=etree.SubElement(pr,'{%s}pos'%MM_NS);pos.set('{%s}val'%MM_NS,'top')
            expr=group.find('{%s}e'%MM_NS);bar.append(expr);group.getparent().replace(group,bar)
    for radical in node.findall('.//{%s}rad'%MM_NS):
        if radical.find('{%s}deg'%MM_NS) is None:
            pr=etree.Element('{%s}radPr'%MM_NS)
            hide=etree.SubElement(pr,'{%s}degHide'%MM_NS);hide.set('{%s}val'%MM_NS,'1')
            radical.insert(0,pr);radical.insert(1,etree.Element('{%s}deg'%MM_NS))
    for accent_limit in list(node.findall('.//{%s}limUpp'%MM_NS)):
        limit=accent_limit.find('{%s}lim'%MM_NS)
        if limit is not None and ''.join(limit.itertext())=='^':
            accent=etree.Element('{%s}acc'%MM_NS)
            pr=etree.SubElement(accent,'{%s}accPr'%MM_NS)
            char=etree.SubElement(pr,'{%s}chr'%MM_NS);char.set('{%s}val'%MM_NS,'̂')
            accent.append(accent_limit.find('{%s}e'%MM_NS))
            accent_limit.getparent().replace(accent_limit,accent)
    for run in node.findall('.//{%s}r'%MM_NS):
        # Explicit math fonts avoid inherited CJK/Latin fallback mixing in Office.
        word_pr=etree.Element('{%s}rPr'%W_NS)
        run.insert(1 if run.find('{%s}rPr'%MM_NS) is not None else 0,word_pr)
        fonts=etree.SubElement(word_pr,'{%s}rFonts'%W_NS)
        for key in ['ascii','hAnsi','eastAsia','cs']:fonts.set('{%s}%s'%(W_NS,key),'Cambria Math')
        token=run.find('{%s}t'%MM_NS)
        if token is not None and token.text=='∣':token.text='|'
        if token is not None and token.text=='~' and r'\sim' in latex:
            token.text='∼'
            style=run.find('{%s}rPr/{%s}sty'%(MM_NS,MM_NS))
            if style is not None:style.set('{%s}val'%MM_NS,'p')
    MATH_RECORD.append(dict(latex=latex,math_text=''.join(node.itertext()),status='CREATED'))
    return node


def text_run(p,text,size=None,bold=False):
    r=p.add_run(text)
    r.font.name='Times New Roman'; r._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'SimSun')
    r.font.color.rgb=RGBColor(0,0,0);r.bold=bold
    if size: r.font.size=Pt(size)
    return r

def unit_element(latex):
    node=math_element(latex)
    for run in node.findall('.//{%s}r'%MM_NS):
        pr=run.find('{%s}rPr'%MM_NS)
        if pr is None:pr=etree.Element('{%s}rPr'%MM_NS);run.insert(0,pr)
        sty=pr.find('{%s}sty'%MM_NS)
        if sty is None:sty=etree.SubElement(pr,'{%s}sty'%MM_NS)
        sty.set('{%s}val'%MM_NS,'p')
    return node


def inline(p,text,size=None,bold=False):
    for part in re.split(r'(\$[^$]+\$)',text):
        if not part:continue
        if part.startswith('$') and part.endswith('$'):p._p.append(math_element(part[1:-1]))
        else:
            # Units and chemical subscripts are also native Office Math, not
            # Unicode pseudo-superscripts or raw TeX in prose/table headings.
            pattern=r'(μg(?:\s*m[−-]3|/m³)|PM(?:2\.5|₂\.₅)|°C)'
            for chunk in re.split(pattern,part):
                if not chunk:continue
                if chunk.startswith('μg'):
                    p._p.append(unit_element(r'\mu\mathrm{g}\,\mathrm{m}^{-3}'))
                elif chunk in ['PM2.5','PM₂.₅']:
                    p._p.append(unit_element(r'\mathrm{PM}_{2.5}'))
                elif chunk=='°C':p._p.append(unit_element(r'\mathrm{°C}'))
                else:text_run(p,chunk.replace('**','').replace('`',''),size,bold)

