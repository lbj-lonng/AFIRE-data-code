"""Write the delivery report only after actual final verification and page review."""
from environment import ROOT, SUB, AUD, BASE
from pathlib import Path
from collections import Counter
import csv, json, hashlib
from datetime import datetime

def read(name):
    with (AUD/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def js(name):return json.loads((AUD/name).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ver=js('verification_summary.json');ind=js('independent_verification_summary.json');num=js('numerical_audit_run.json')
    checks=read('supplement_verification.csv');visual=read('visual_review.csv')
    assert not any(r['status'] in ('FAIL','NOT_RUN') for r in checks), 'Final aggregate verification still has an unclosed mechanical gate'
    assert len(visual)==60 and all(r['scoped_status']=='PASS' for r in visual)
    assert ind['cell_checks'].get('FAIL',0)==0 and ind['source_copy_checks'].get('FAIL',0)==0
    assert ind['scope_findings'].get('FAIL',0)==0 and not num['failures']
    identity=js('maintext_sync_integrity.json')
    assert sha(identity['source'])==identity['source_sha256']
    assert sha(identity['output'])==identity['output_sha256']
    history=read('history_source_manifest.csv');migration=read('version_content_migration.csv')
    gates=[
        ('1 版本覆盖','PASS',f'{len(history)}个历史科学来源文件、{len(migration)}条迁移记录；重复副本不作为独立证据。'),
        ('2 范围一致','PASS','正式研究记录2009—2020、仅五类结局；ACS/训练/产品/参考文献年份真实保留且与观察期分开。'),
        ('3 数值一致','PASS',f'135行A—E、48个非键字段及样本/数组身份核验；{num["numerical_checks"]}项数值检查无失败，显示值与完整精度分存。'),
        ('4 校正一致','PASS','A块原七项Holm保存值未重算；B—E未校正P、普通95% CI及事后范围风险明确。'),
        ('5 样本一致','PASS','共同样本3062行顺序/键/30份数组一致；四验证法同298组、2128单元；州县72对。'),
        ('6 完整性与主文解释','PARTIAL','SI全部25条件关联、敏感性及三项包含诊断完整；作者新摘要删掉限定，需要作者决定最小恢复，未擅自改结论。'),
        ('7 文献与引用','PASS','12条独立文献身份核验；首引顺序1—12；22表/7图/12式组连续；19段21处正文SI引用同步。'),
        ('8 来源与代码','PARTIAL','已交付源值/字段/脚本/哈希链；部分SES/火灾/环境产品原始提取、许可及仓库仍缺，不等于完整从头实验可复现。'),
        ('9 原文件保护','PARTIAL','代理未写任何旧源稿/实验输入，全部无未解释变化；1份作者稿执行期间外部更新，已记录并重新采用最新内容，不能称全部初始哈希相同。'),
        ('10 视觉与双语','PARTIAL','SI的CN24/EN26页全部最终逐页PASS；10页同步主文已审，引用布局通过，但原稿编辑提示/第2页留白仍保留。')
    ]
    with (AUD/'acceptance_checklist.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['item','status','evidence_and_boundary']);w.writerows(gates)
    gate_md='\n'.join('| '+ ' | '.join(row)+' |' for row in gates)
    native=js('build_CN.json')['native_math_objects']
    report=f'''# AFIRE Supplement 整合交付报告

完成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}。

**交付状态：材料已生成并通过最终机械/视觉核验；全文投稿就绪状态仍为PARTIAL。** 未闭合的是作者科学表述决策、部分上游来源和发布条件，不是缺失中英文成稿。不能将本报告当作模型重估、外部投稿或数据公开完成证明。

## 文件

新目录：`{ROOT}`。

- [中文Word](submission/Supplementary_Information_CN.docx) / [中文PDF](submission/Supplementary_Information_CN.pdf)：24页。
- [English Word](submission/Supplementary_Information_EN.docx) / [English PDF](submission/Supplementary_Information_EN.pdf)：26页。
- [最小引用同步正文](submission/Main_Text_CN_SI_links_synced.docx) / [对应PDF](submission/Main_Text_CN_SI_links_synced.pdf)：10页。
- [源数据说明](submission/source_data/README.md)、[独立数据附件](submission/supplementary_data/README.md)、[图件](submission/figures)、[实际重建命令](scripts/README.md)。

最终含7节Methods、6节Notes、必要Discussion、22张原生可编辑Word补表、7张补图、12组编号原生公式、12条独立参考文献和3份Supplementary Data。每份Word含{native}个原生Office Math对象（含行内单位/公式）；完整LaTeX另附。Data 1/2/3分别49/72/81行。图源为矢量PDF/SVG和600 dpi PNG，SI实际嵌入约170 mm；183 mm独立母版不是按179 mm生产宽度缩放的最终上传单图。需要独立生产图时须按官方尺寸缩放并复检，不影响已通过的SI嵌入页。

## 实际正文身份与最小修改

采用`{identity['source']}`，作者最新修改时间2026-09-16 23:31:04（本地）。SHA256：`{identity['source_sha256']}`。

执行期间发现源稿由作者外部更新；保留初始身份/差异记录并从最新稿重做同步。当前结构为两项Results、四张主图，而非旧三项Results或七结局全文。仅改{identity['changed_paragraphs']}个段落内{identity['changed_references']}处补充引用；其他{identity['unchanged_package_parts']}个ZIP部件、主图/公式XML与其他正文文字保持不变。输出SHA256：`{identity['output_sha256']}`。具体见maintext_changes.md、maintext_si_only.diff及maintext_sync_integrity.json。

## 版本整合与科学纠错

盘点{len(history)}个历史科学来源文件，形成{len(migration)}条内容迁移记录。覆盖早期handoff/verified包、重构版、七结局版、三研究点版、主图优化版、州到县版、9.15四主图整合版、当前五结局版及根目录补充方法，并按需只读追溯原实验。旧材料按保留、补充、合并去重、纠正、内部追溯、范围外或待证据分流，不直接拼接旧SI。

关键补回/合并：州等权与县人口加权的不同定义；72对州县桥接；贫困代理与固定县级劣势的区别；火灾记录/归属/潜在重复；1—9主分配的固定EB与动态规划；0—19、100份、整年留出的伪抑制验证；四法全部六项评价指标及五类分层；完整八分支公式/真实共同样本；LST质量规则/配对样本；符合当前时间和身份的历史COPD辅助模型。

关键纠正：离散度分子减平均完整响应而非拟合均值；传统Rubin而非Barnard–Rubin；真实FMI；主固定EB使用历史全时期、并非留目标年；旧地理表105行/县分母只留内部审计；旧范围验证/旧全国趋势/旧FDR不回流。三项包含关系数组不一致、15个负向/10个跨零条件区间、定向删除后不利结果均保留，未包装成联合后验或额外死亡证据。

找到的新增上游证据包括30份县级CDC导出与15,360行面板、五份州级导出与360组总量一致，实际州查询HTML元数据，以及固定EB权重文件与原B1输入hash一致。县级原始响应/许可、全部SES构造、火灾提取排名去重和部分环境产品链仍未全闭合。原七项参考交互家族的Holm数值保留，未改为五项或宣称预注册。

## 实际核验结果

- 冻结数值：{num['numerical_checks']} PASS；范围：{num['scope_checks']} PASS。135行A/B/C/D/E=5/25/40/25/40及所有48个非键字段逐键比对；数组仅内存只读核验，未导出受限分配。
- 独立Word逐格：{ind['cell_checks'].get('PASS',0)} PASS；源复制/历史选择/种子身份：{ind['source_copy_checks'].get('PASS',0)} PASS；{ind['scope_containers'].get('SCANNED',0)}个最终文本容器扫描未见取消结局的ID或名称。二进制未做OCR，SVG/PDF文本已扫描；其边界单列在独立报告。
- 最终总检：{json.dumps(ver['checks'],ensure_ascii=False)}；双语数值/公式核心事实：{json.dumps(ver['bilingual'],ensure_ascii=False)}。实际12组原生OMML与公式源、7份嵌图PNG hash、最终PDF与渲染副本、DOCX与渲染输入hash分别认证。
- 最终原文件hash：{json.dumps(ver['source_hashes'],ensure_ascii=False)}。1个外部作者修改有明确记录；无代理导致的未解释源文件变化。
- 视觉：CN24页、EN26页逐页实际查看，合计50页全部PASS；7图的14个双语嵌入页另有独立复核。同步主文10页也实际查看，引用修改布局通过；继承原稿编辑提示/留白的状态如实PARTIAL。所有60页均绑定末次PNG哈希，未套用旧渲染PASS。
- 来源与文献：12条文献身份核对，数据字典230字段覆盖61个规范CSV；文献/产品身份不冒充原始下载批次或再分发许可。

|验收项|状态|依据与边界|
|---|---|---|
{gate_md}

## 投稿前仍须作者处理

最重要的是最新摘要删除了不确定性限定。本轮未越权恢复，也没有把该冲突标为通过。建议作者批准的最小恢复句：**“高劣势水平下的条件关联区间仍跨零，定向删除高影响年份或地区后不确定性增大。”** 其余因果措辞/选区依据、正文编辑提示、上游资料、作者/伦理/许可/仓库事项见[作者清单](audit/author_action_needed.md)及[未闭合事项](audit/unresolved_items.md)。

本轮未拟合死亡模型、训练EB、生成分配、重算SES/IQR、多重校正、新P值/CI或bootstrap；没有上传任何网站或仓库。历史源文件只读，全部输出/缓存/渲染在本新目录；旧版不会因本次交付被覆盖。唯一本轮发现的旧公共地理表副本从**本新目录**的公开源数据移到内部audit并保留字节相同备份，未删除任何历史版本。

## 重建/核验

本机可用的依赖路径、真实脚本顺序、完整PowerShell命令及隔离portable LibreOffice说明均见[scripts/README.md](scripts/README.md)。简要命令如下，先按README设置`$afirePython`与`$afireScripts`：

```powershell
& $afirePython -X utf8 "$afireScripts\\build_supplement.py"
& $afirePython -X utf8 "$afireScripts\\render_documents.py" Supplementary_Information_CN.docx Supplementary_Information_EN.docx
# 必须重新逐页目检并记录当前hash，旧视觉PASS不能自动继承。
& $afirePython -X utf8 "$afireScripts\\verify_history_source_hashes.py"
& $afirePython -X utf8 "$afireScripts\\verify_cell_and_scope.py"
& $afirePython -X utf8 "$afireScripts\\verify_supplement.py"
```

脚本是本地冻结证据的重排/绘图/核验流程，不是独立完整实验环境；部分上游源与依赖仍位于原路径。下一版本必须另建目录并检查硬编码OUT，不能不加检查地运行旧run_all.py。重渲染后的新页未经查看时，verify_supplement会显示NOT_RUN，不能发布为全PASS。
'''
    (ROOT/'FINAL_REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps({'report':str(ROOT/'FINAL_REPORT.md'),'pages':len(visual),'mechanical_checks':ver['checks'],'delivery':'COMPLETE','submission_readiness':'PARTIAL_AUTHOR_AND_SOURCE_ACTIONS'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
