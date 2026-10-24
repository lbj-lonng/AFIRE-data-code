"""Seal a delivery only against already-recorded actual visual review hashes."""
from environment import ROOT, SUB, AUD, PREV
from pathlib import Path
import pandas as pd
import hashlib, json, datetime
import fitz

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def run():
    reviewed=pd.read_csv(AUD/'visual_review.csv')
    assert len(reviewed)==57 and reviewed.review_status.eq('PASS').all()
    assert all(sha(ROOT/p)==s for p,s in zip(reviewed.file, reviewed.sha256))
    scope=pd.read_csv(AUD/'scope_consistency_check.csv')
    assert len(scope)==322 and scope.status.eq('PASS').all()
    table=pd.read_csv(AUD/'supplement_table_value_check.csv')
    assert len(table)==135 and table.Word_matches_Source_Data.all() and table.rounded_estimate_CI_P_match_frozen_result.all()
    inputs=pd.read_csv(AUD/'INPUT_MANIFEST.csv')
    assert inputs.source_unchanged.all() and inputs.frozen_copy_matches.all()
    pages=[]
    for d in sorted(SUB.glob('*.docx')):
        directory=AUD/'rendered_pages'/d.stem
        count=len(list(directory.glob('page-*.png')))
        expected=28 if d.name.startswith('Supplementary') else 9
        assert count==expected
        pdf=fitz.open(directory/(d.stem+'.pdf'))
        assert len(pdf)==expected
        pages.append({'document':d.name,'pages':count,'docx_sha256':sha(d),'all_pages_actually_viewed':True})
    (AUD/'document_visual_summary.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
    initial=json.loads((AUD/'supplement_build_check.json').read_text(encoding='utf-8'))
    initial['status']='STRUCTURAL_AND_ACTUAL_VISUAL_PASS'
    initial['table_source_checks']='supplement_table_value_check.csv: all 135 rows verified'
    initial['tables_135_rows']=[{'table':k,'rows':int(len(v))} for k,v in table.groupby('table')]
    initial['visual_review']='visual_review.csv: all 28 SI pages; hashes checked before sealing'
    (AUD/'supplement_build_check.json').write_text(json.dumps(initial,ensure_ascii=False,indent=2),encoding='utf-8')
    notes='''# 最终视觉与程序核验说明

本轮主代理实际打开检查了干净版9页、讨论标黄版9页、补充材料28页，以及四张主图和七张补图的完整最终尺寸预览。不是仅提取文字或抽查缩略图。共57条PNG哈希记录见visual_review.csv。干净版1—7页及SI1—8页在后续渲染中与已检查图像哈希一致；干净版8—9页及整份标黄版在最终排版后再次实际查看。

发现并修正：新正文段落继承异常字体；参考文献最后一条单独占页（仅收紧参考文献段间距，未缩小正文字号）；补图S5图例与数据条距离不足（移到轴下方）；旧Word中未使用的旧图关系。修正后重新渲染并复查。

保留最近完整稿的版式。补充图单独成页，S1—S4五面板高度足以阅读完整区间；S5/S6较短的独立图页留白属有意的逐图交付版式。长表连续跨页，重复表头，未裁掉行或压缩科学内容。所有图的PDF宽183 mm、最小文字7 pt；四主图600 dpi PNG/TIFF，补图600 dpi PNG；PDF/SVG保留矢量及可编辑文本。Word缩放后也已逐图查看。

原始静态检查不是全部PASS，原报告完整保留：单文件检查器无法追踪shared_style.py的导入设置和导出循环，把183/25.4误读成183英寸，也把audit-only 180 dpi预览误当作正式位图。static_lint_review.csv逐项给出实际字体、183 mm PDF、SVG文本、600 dpi PNG和代码证据，未篡改原始失败记录。

PDF碰撞原始结果：9图PASS；图1和图2各1条WARN、0条FAIL。已逐项查看P10—P90图例与阴影：阴影的矩形包围盒覆盖左上图例，但实际多边形只在右端高年份接近上缘，左上方没有数据或文字遮挡。collision_warning_review.csv保留实际警告与接受原因及PDF哈希。所有适用的多面板对齐门通过；单面板S6/S7不冒称通过多面板对齐。

scope_consistency_check.csv的322项范围核验全部通过。额外独立核对135行补表：Word与Source Data逐单元一致，估计、完整CI、样本数、原始P和原Holm P按实际展示精度与冻结模型结果一致。没有将四舍五入一致误称为重新拟合验证；未取整原模型参数已另做逐值相等检查。

所有输入源文件哈希复查未变；交付清单的哈希不包含它自身。实际未进行死亡拟合、插补、训练、重新标准化、重新多重校正或任何新增推断。上游资料与投稿声明仍有PARTIAL项，不以版式/程序通过替代来源完整性。
'''
    (AUD/'quality_review_notes.md').write_text(notes,encoding='utf-8')
    command=f"& 'C:\\Users\\86189\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' '{ROOT}\\scripts\\run_all.py'"
    report=f'''# AFIRE范围统一完成报告

本轮修改、四主图、补充材料及核验已实际完成，全部位于本新目录。未覆盖旧稿或实验。投稿来源条件仍为PARTIAL，并非主图数据缺失。

## 使用版本与研究范围

编辑起点为最近完整版本：{PREV}。主文来自该版05_manuscripts/Main_Text_CN_clean.docx，并使用与其配套的SI、四图及结果。未退回早稿。

观察期为2009—2020年，共12年。仅展示COPD、慢性下呼吸道疾病、呼吸系统疾病、循环系统疾病、缺血性心脏病，按该顺序排列。ICD分别保持J40—J44、J40—J47、J00—J98、I00—I99、I20—I25；父类不扣除任何组成诊断，不相加为不重复死亡数。真实2006—2010年基线、历史训练时期、产品和参考文献年份按用户要求准确保留。

## 已重汇总与直接复用

逐键核实588个有观测州—年、3,072个唯一县—年、15,360条死亡记录、3,328条受抑制记录、325个公开零值、360个州—年—死因组、每县60条地图分母、72对跨尺度比较。所有死因余量、记录比例和地图数值均从当前范围重汇总。

验证有充分逐单元源数据：四方法使用相同2,128个评价单元和298组。已按单元重新汇总MAE、RMSE、覆盖率、宽度、CRPS和区间评分，未训练或重新分配。固定EB MAE为1.971983，层级EB为1.960028；固定EB CRPS为1.391503，层级EB为1.400846，正文不再写固定方法在所有指标上最优。固定EB覆盖率为97.5564%。

归档火灾名单筛为81条记录、89次州归属；六州55次归属涉及53条不同目录记录。不是新生成全国Top100；没有合并疑似重复或重新排名。

直接复用五类已有135行健康结果（A/B/C/D/E为5/25/40/25/40），beta、SE、完整CI、P值和自由度与原表一致。图4d五类均核对真实3,062条共同样本的键、次序和30份分配数组，不以3,072条参考样本替代。原烟雾IQR、SES、负二项、县/年份固定效应、人口offset、县聚类和Rubin合并均保持。

沿用已存Holm调整值，真实原检验家族大小仍为7，不改称五项校正，不重新计算。保留全部五类自身25项条件对比（15项普通区间全负、10项跨零、0项全正）、删样本不利结果，以及三种保留包含关系的数组不一致。

## 文件与核验

submission中有三份Word：正文干净版9页、同内容讨论逐句标黄版9页、完整SI 28页；另有中英文四图图注、原生可编辑Word数学对象和独立equations.tex。四张主图均已从当前Source Data重绘，保留a—d结构；七张补图及24项编号补表同步完成。模型和显著性均未重算。

322项范围程序检查通过；135行Word/CSV/冻结结果逐项一致；46页Word和11图已实际目检，修复参考文献孤页和S5图例问题。原始静态检查及2条已目检解释的PDF包围盒警告如实保留，不宣称所有工具均返回PASS。详见audit/quality_review_notes.md及各CSV。

使用本地nature-writing、nature-statistics、nature-figure及文档等技能约束了证据边界、主文与补充材料分工、完整区间和原生公式，并以实际渲染检查完成交付；数据可用性核验没有把本地文件误写成已公开入库。

## 投稿前仍缺资料

需要火灾目录原始提取日期/查询/版本及全库Rank和去重脚本；县级综合劣势指数的完整组成、权重、缺失处理及NHGIS/ACS提取档案；本批CDC县/州查询、下载批次及再分发许可；部分环境与人口协变量的精确版本、单位和聚合链；作者、贡献、资助、利益冲突、伦理认定，以及公开仓库永久标识和许可。具体清单在audit/unresolved_items.md。尚无授权公开上传，未对外发布任何数据。

## 重建

新目录：{ROOT}

PowerShell一条命令：

```powershell
{command}
```

run_all.py只重建本轮描述汇总、图文和核验，不触发死亡拟合或插补。最后核对已记录的视觉哈希；若任何页面改变，会要求重新目检，不自动赋予新页面视觉通过。
'''
    (ROOT/'FINAL_REPORT.md').write_text(report,encoding='utf-8')
    status={'reporting_revision':'COMPLETE', 'submission_provenance':'PARTIAL',
            'scope_checks':322, 'scope_failures':0, 'supplement_result_rows_checked':135,
            'Word_pages_actually_inspected':46, 'figure_previews_actually_inspected':11,
            'original_inputs_unchanged':len(inputs), 'not_run':['death_refit','imputation','retraining','rescaling','new_Holm_or_CI_or_bootstrap'],
            'sealed_at':datetime.datetime.now().astimezone().isoformat()}
    (AUD/'delivery_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    files=[*sorted(SUB.rglob('*')), *sorted((ROOT/'scripts').rglob('*')), ROOT/'README.md', ROOT/'FINAL_REPORT.md']
    pd.DataFrame([{'file':str(p.relative_to(ROOT)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':sha(p)}
                  for p in files if p.is_file() and '__pycache__' not in p.parts]).to_csv(AUD/'DELIVERY_MANIFEST.csv',index=False)
    print(json.dumps(status,ensure_ascii=False))

if __name__=='__main__': run()
