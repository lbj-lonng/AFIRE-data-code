from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from v7_common import REPORTS, TABLES


def fmt(value, digits=3):
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "NA"


def row_text(row: pd.Series) -> str:
    return (
        f"{row.get('label', row.get('model_id'))}: "
        f"{fmt(row.get('percent_change'))}% "
        f"(95%CI {fmt(row.get('percent_change_ci_low'))}% to "
        f"{fmt(row.get('percent_change_ci_high'))}%), "
        f"p={fmt(row.get('p_value'), 4)}"
    )


def main() -> None:
    status_path = TABLES / "model_status_v7.csv"
    interaction_path = TABLES / "interaction_summary_v7.csv"
    if not status_path.exists() or not interaction_path.exists():
        raise FileNotFoundError("请先运行聚合脚本")
    status = pd.read_csv(status_path)
    interactions = pd.read_csv(interaction_path)
    marginal_path = TABLES / "marginal_effects_v7.csv"
    marginal = pd.read_csv(marginal_path) if marginal_path.exists() else pd.DataFrame()

    completed = int(status["status"].eq("completed").sum()) if not status.empty else 0
    incomplete = int(status["status"].eq("incomplete").sum()) if not status.empty else 0
    blocked = int(status["status"].eq("blocked").sum()) if not status.empty else 0

    lines = [
        "# Afire v7 最终实验自动报告",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 一、运行完成度",
        "",
        f"- 完成模型：{completed}",
        f"- 插补数不足模型：{incomplete}",
        f"- 数据或设计阻塞模型：{blocked}",
        "",
    ]
    if incomplete or blocked:
        lines += [
            "> 当前仍有未完成模型，不能宣布实验全部完成。请查看 `results/tables/model_status_v7.csv` 和 `model_failures_v7.csv`。",
            "",
        ]
    else:
        lines += [
            "> 所有选定模型均达到最低多重插补成功数，可以进入论文结果整理阶段。",
            "",
        ]

    key_ids = [
        "O03_state_year_PPML_2009_2020",
        "O10_temperature_adjusted_2009_2020",
        "O11_full_environment_2009_2020",
        "F01_temperature_exclude_2020",
        "F02_full_environment_exclude_2020",
        "F03_nonwildfire_PM25_2009_2020",
        "F04_nonwildfire_PM25_exclude_2020",
        "F05_poverty_modifier_2009_2020",
        "F06_period_2009_2016",
        "F07_period_2017_2020",
    ]
    key = interactions.loc[interactions["model_id"].isin(key_ids)]
    lines += ["## 二、核心模型与关键敏感性分析", ""]
    for _, row in key.iterrows():
        lines.append(f"- {row_text(row)}")
    lines.append("")

    lines += ["## 三、边际效应", ""]
    if marginal.empty:
        lines.append("未生成边际效应。")
    else:
        for model_id, x in marginal.groupby("model_id"):
            lines.append(f"### {x['label'].iloc[0]}")
            lines.append("")
            for _, row in x.sort_values("ses_sd").iterrows():
                lines.append(
                    f"- SES={row['ses_sd']:+.0f} SD：{fmt(row['percent_change'])}% "
                    f"(95%CI {fmt(row['percent_change_ci_low'])}% to {fmt(row['percent_change_ci_high'])}%)"
                )
            lines.append("")

    lines += [
        "## 四、论文结论判定规则",
        "",
        "1. 交互项表示SES每增加1 SD时，野火PM₂.₅每增加1 IQR对应的死亡率关联改变幅度，不是弱势县的直接死亡率效应。",
        "2. 直接效应应引用边际效应表，而不是仅引用交互项。",
        "3. 州×年份PPML、剔除2020、非野火PM₂.₅、逐年剔除和逐州剔除共同决定结论稳健性。",
        "4. 州分层模型属于探索性分析，尤其是县数较少的州，应避免过度解释。",
        "5. 若提前一年安慰剂仍接近显著，应在讨论中保留残余时间混杂的限制。",
        "",
        "## 五、最终输出位置",
        "",
        "- `results/tables/paper_main_and_key_sensitivity_v7.csv`",
        "- `results/tables/marginal_effects_v7.csv`",
        "- `results/tables/leave_one_year_out_v7.csv`",
        "- `results/tables/leave_one_state_out_v7.csv`",
        "- `results/tables/state_specific_v7.csv`",
        "- `results/tables/secondary_outcomes_v7.csv`",
        "- `results/figures/`",
    ]
    report_path = REPORTS / "Afire_v7_final_experiment_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
