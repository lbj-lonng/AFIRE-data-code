"""Record human-in-the-loop page-image observations, not an automated visual PASS."""
from pathlib import Path
from datetime import datetime
import csv,hashlib,json

OUT=Path(__file__).resolve().parents[1]
RENDER=OUT/'audit/render/Main_Text_CN_SI_links_synced'
SOURCE=Path(r'D:\postgraduate\wildfire\9.10\9.15\AFIRE_2009_2020_five_outcomes_20260915_194616\submission\Main_Text_CN_2009_2020_five_outcomes_clean.docx')
EXPECTED='d91b9515fc5129c5b1970767d094109961027fbd9d0ce623993395ea0399c55b'

# These notes were entered after actual view_image inspection of page-1 through page-10.
NOTES={
1:('PARTIAL','PASS','PARTIAL','题名、摘要及引言清晰，未见裁切、缺字或重叠；作者黄底相邻两研究概述段均完整。','作者单位待补；重复引言和括号提示保留。23:31作者删去摘要关键不确定性限定，需作者决定恢复；非此次引用同步改写。'),
2:('PARTIAL','PARTIAL','PARTIAL','Results 1和补充表7及补充数据3引用完整、自然换行；未挤压或溢出。','下方大面积留白，图1整块在下一页；保留既有图件/分页流，不在仅同步引用任务内调整。标题内作者经济因果提示尚未处理。'),
3:('PARTIAL','PASS','PARTIAL','图1四面板、图注和随后县尺度正文均完整；补充数据1和3及表7、表6引用可读；无切图或越界。','县段末黄底红字“为什么选这六个州”作者提示仍在；未擅删。'),
4:('PASS','PASS','PASS','图2四面板、图注、Results 2标题及两段正文完整；补充方法4和表9—10清晰；页底无裁切。','无本页新增视觉问题。'),
5:('PASS','PASS','PASS','图3地图、双分母条形图、误差和覆盖率面板完整；补充表9—10、15、16、17、19、22换行可读，未遮挡图文。','图注和正文略密但字形清楚；五结局条件区间跨零的限定仍在正文。'),
6:('PARTIAL','PASS','PARTIAL','图4四面板及底部图例完整、置信区间未截断；图注表15—19引用清晰；讨论段均在页边界内。','黄底/红字和括号编辑提示是作者原有内容；有关“经济与暴露无关”过强提示仍需作者裁定。'),
7:('PARTIAL','PASS','PARTIAL','讨论、结论、Methods及页底续段正常衔接；补充表18、12、7、数据3及方法5均完整显示。','作者“说明可能是因经济造成的”黄底提示保留；没有新增重叠或缺字。'),
8:('PASS','PASS','PASS','方法、式1和式2原生公式完整，符号/上下标可辨；补充表1、2、6、数据1、2、方法4均可读。','式3引导句位于本页末而公式位于下页，属当前页流；未发生公式截断。'),
9:('PARTIAL','PASS','PARTIAL','式3三行完整，统计方法、可用性段和参考文献1—5均无重叠；补充表22、18—19可读。','数据/代码仓库和作者声明仍有明确待补占位；不是最终投稿清稿。'),
10:('PASS','PASS','PASS','参考文献6—30完整，DOI和长URL正常换行，页码及边距正常；未见缺字或截断。','本页无SI引用，无新增视觉问题。'),
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    rows=[]
    for page,(overall,layout,content,observed,residual) in NOTES.items():
        p=RENDER/f'page-{page}.png'
        rows.append({'page':page,'page_image':str(p),'sha256':sha(p),'inspection':'Actual view_image original-page inspection','status':overall,'layout_status':layout,'si_reference_layout_status':'PASS','content_readiness':content,'observation':observed,'retained_author_or_layout_issue':residual})
    with (OUT/'audit/visual_review_maintext.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    source_hash=sha(SOURCE)
    record={'reviewed_at_local':datetime.now().astimezone().isoformat(),'pages_actually_inspected':list(NOTES),'method':'view_image of every original rendered page; no contact-sheet-only sign-off','si_reference_layout_status':'PASS','overall_document_status':'PARTIAL','source':str(SOURCE),'expected_latest_source_sha256':EXPECTED,'source_sha256_at_visual_review':source_hash,'source_still_current':source_hash==EXPECTED,'render_pdf_sha256':sha(RENDER/'Main_Text_CN_SI_links_synced.pdf'),'synchronized_docx_sha256':sha(OUT/'submission/Main_Text_CN_SI_links_synced.docx'),'limitations':'Author inline notes, publication placeholders, abstract boundary deletion and inherited page-2 whitespace were retained under minimal-reference-only scope.'}
    (OUT/'audit/maintext_visual_review_summary.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
