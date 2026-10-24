"""Manual observations entered after actual original-page view_image inspection."""
from pathlib import Path
import csv,hashlib
OUT=Path(__file__).resolve().parents[1]
DOCX=OUT/'submission/Supplementary_Information_CN.docx'
EXPECTED='2b7fcf781bca332b6ace74b0597f75b8ed43f1d34247d680a4cba8b34901b990'
NOTES=[
'题名、方法1—2及公式1—2完整；公式上下标/分式可读，页底正文正常续页。',
'方法3—4与公式3—4完整；长定义自然换行，未见公式残缺、重叠或越界。',
'公式5—7及方法5—6完整；DP分母和求和上下标均保留，标题没有孤立。',
'公式8—12均完整且与标签同页；方法7开头有正文相随，没有缺失数学符号或页底裁切。',
'方法7续文及说明1—5连续排版；各标题有正文，页底段落正常延续。',
'说明5—6、补充讨论、表1及表2起始均可读；表2标题/说明和首行同页。',
'表2跨页重复表头清楚；表3完整；表4标题说明及首四行同页。',
'表4续页重复表头；表5—6完整，表7标题说明和数据同页；无孤立表题。',
'表7末三行有重复表头；表8完整；表9主体整齐，无表格行截断。',
'表9最后一行有重复表头；表10及表11完整、标题说明和表体相连。',
'表12—15标题与表体同页，列宽充分；负号、科学计数P值、种子和Holm列清楚。',
'表16全25行完整；表17标题说明及首七行相连，普通CI及P值未越界。',
'表17重复表头并连续至末行；表18标题说明和首三行同页，无截断。',
'表18续页完整；表19标题说明及起始数据相连；负区间和样本数均可读。',
'表19续页重复表头并完整结束；表20完整，未出现孤立标题或空白页。',
'表21历史模型定义、全部11行及表22均完整；图件区从下一页开始，保留合理区段留白。',
'补充图1标题、六州热图、颜色条及完整图注同页；无切图；一图一页留白不影响阅读。',
'补充图2标题、全部六州箱线/散点及完整图注同页；图例、样本量标签清楚。',
'补充图3双面板、分母、图例与完整图注同页；全部条形、轴及数值无裁切。',
'补充图4五面板、普通CI限定与完整图注同页；最左置信限和零参考线均显示。',
'补充图5五面板八模型及完整图注同页；模型标签不重叠，全部区间可见。',
'补充图6五面板及完整图注同页；IHD负向长区间未截断，不利结果完整显示。',
'补充图7严格/宽松LST五面板及完整图注同页；底部说明和全部区间完整。',
'独立参考文献1—12全部完整；长URL自然换行，未见缺字、裁切或额外空白页。',
]
assert hashlib.sha256(DOCX.read_bytes()).hexdigest()==EXPECTED
rows=[]
for i,note in enumerate(NOTES,1):
    p=OUT/f'audit/render/Supplementary_Information_CN/page-{i}.png'
    rows.append({'page':i,'page_image':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'inspection':'Actual view_image original-page inspection; all 24 pages individually inspected','status':'PASS','observation':note,'docx_sha256':EXPECTED})
with (OUT/'audit/visual_review_CN.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('24 actual page inspections recorded; visual PASS, scientific source limits remain separately documented.')
