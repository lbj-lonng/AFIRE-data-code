from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from v7_common import FIGURES, TABLES


def save_forest(data: pd.DataFrame, label_col: str, filename: str, title: str) -> None:
    if data.empty:
        return
    data = data.dropna(subset=["percent_change", "percent_change_ci_low", "percent_change_ci_high"]).copy()
    if data.empty:
        return
    data = data.sort_values("percent_change")
    y = np.arange(len(data))
    x = data["percent_change"].to_numpy(float)
    low = x - data["percent_change_ci_low"].to_numpy(float)
    high = data["percent_change_ci_high"].to_numpy(float) - x
    fig, ax = plt.subplots(figsize=(9, max(4, 0.38 * len(data) + 1.5)))
    ax.errorbar(x, y, xerr=np.vstack([low, high]), fmt="o", capsize=3)
    ax.axvline(0, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(data[label_col].astype(str))
    ax.set_xlabel("PM₂.₅ × SES interaction (% change per IQR and 1-SD disadvantage)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(FIGURES / filename, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    interactions_path = TABLES / "interaction_summary_v7.csv"
    if not interactions_path.exists():
        raise FileNotFoundError("请先运行 scripts/v7_aggregate.py")
    interactions = pd.read_csv(interactions_path)

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
    key = interactions.loc[interactions["model_id"].isin(key_ids)].copy()
    save_forest(key, "label", "Fig_v7_1_key_models.png", "Primary and key sensitivity models")

    for group, filename, title in [
        ("leave_one_year", "Fig_v7_2_leave_one_year.png", "Leave-one-year-out analysis"),
        ("leave_one_state", "Fig_v7_3_leave_one_state.png", "Leave-one-state-out analysis"),
        ("state_specific", "Fig_v7_4_state_specific.png", "State-specific exploratory estimates"),
        ("secondary_outcomes", "Fig_v7_5_secondary_outcomes.png", "Secondary outcome models"),
    ]:
        x = interactions.loc[interactions["group"].eq(group)].copy()
        save_forest(x, "label", filename, title)

    marginal_path = TABLES / "marginal_effects_v7.csv"
    if marginal_path.exists():
        marginal = pd.read_csv(marginal_path)
        if not marginal.empty:
            for model_id, x in marginal.groupby("model_id"):
                x = x.sort_values("ses_sd")
                fig, ax = plt.subplots(figsize=(7, 5))
                ax.errorbar(
                    x["ses_sd"], x["percent_change"],
                    yerr=np.vstack([
                        x["percent_change"] - x["percent_change_ci_low"],
                        x["percent_change_ci_high"] - x["percent_change"],
                    ]),
                    fmt="o-", capsize=4,
                )
                ax.axhline(0, linewidth=1)
                ax.set_xlabel("Baseline socioeconomic disadvantage (SD)")
                ax.set_ylabel("Mortality rate change per wildfire PM₂.₅ IQR (%)")
                ax.set_title(str(x["label"].iloc[0]))
                fig.tight_layout()
                fig.savefig(FIGURES / f"Fig_v7_marginal_{model_id}.png", dpi=300, bbox_inches="tight")
                plt.close(fig)
    print(f"Figures saved to {FIGURES}")


if __name__ == "__main__":
    main()
