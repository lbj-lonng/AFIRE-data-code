#!/usr/bin/env python3
"""Rebuild four simple evidence plots from the packaged CSV files."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures/rebuilt_from_package"
OUT.mkdir(parents=True, exist_ok=True)

# R1 state-scale exposure and inequality
a = pd.read_csv(ROOT / "data/result1/annual_exposure_inequality.csv")
fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.plot(a.year, a.population_weighted_smoke_pm25, marker="o", color="#2B6CB0")
ax.set_xlabel("Year"); ax.set_ylabel("Population-weighted smoke PM2.5 (ug/m3)", color="#2B6CB0")
ax2 = ax.twinx(); ax2.plot(a.year, a.gini_smoke_pm25, marker="s", color="#DD6B20")
ax2.set_ylabel("Exposure Gini", color="#DD6B20")
fig.tight_layout(); fig.savefig(OUT / "R1_state_exposure_and_Gini.png", dpi=220); plt.close(fig)

# R1 four design groups and omission estimates
d = pd.read_csv(ROOT / "data/result1/joint_extreme_design_diagnostics.csv")
o = pd.read_csv(ROOT / "data/result1/targeted_omission_models.csv")
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
axes[0].barh(d.group, 100*d.residualized_interaction_ss_share, color="#4C78A8")
axes[0].set_xlabel("Residualized interaction-design SS share (%)")
y = np.arange(len(o)); axes[1].errorbar(o.interaction_percent, y, xerr=[o.interaction_percent-o.CI_lower, o.CI_upper-o.interaction_percent], fmt="o", color="#E45756", capsize=3)
axes[1].axvline(0,color="black",lw=.8); axes[1].set_yticks(y, o.scenario); axes[1].set_xlabel("Smoke x SES interaction (%)")
fig.tight_layout(); fig.savefig(OUT / "R1_extreme_design_and_omission.png", dpi=220); plt.close(fig)

# R2 pseudo-suppression validation
s = pd.read_csv(ROOT / "data/result2/pseudo_suppression_validation_summary.csv")
s = s[s.scope == "all_outcomes"].sort_values("MAE")
fig, ax = plt.subplots(figsize=(7.2, 4.2)); x=np.arange(len(s))
ax.bar(x-.2, s.MAE, .2, label="MAE"); ax.bar(x, s.RMSE, .2, label="RMSE"); ax.bar(x+.2, s.mean_CRPS, .2, label="CRPS")
ax.set_xticks(x, s.method, rotation=20, ha="right"); ax.legend(frameon=False); fig.tight_layout()
fig.savefig(OUT / "R2_imputation_validation.png", dpi=220); plt.close(fig)

# R3 common-sample covariate models
m = pd.read_csv(ROOT / "data/result3/common_covariate_models_by_imputation.csv")
m = m[m.imputation_scenario == "fixed_EB_B0_0_9"].copy()
order = ["M0","M1","M2","M2P","M3"]; m["ord"] = m.model_family.map({v:i for i,v in enumerate(order)}); m=m.sort_values("ord")
y=np.arange(len(m)); fig,ax=plt.subplots(figsize=(7.2,4.2))
ax.errorbar(m.interaction_percent,y,xerr=[m.interaction_percent-m.CI_percent_lower,m.CI_percent_upper-m.interaction_percent],fmt="o",color="#2F855A",capsize=3)
ax.axvline(0,color="black",lw=.8); ax.set_yticks(y,m.model_family); ax.set_xlabel("Smoke x SES interaction (%)"); fig.tight_layout()
fig.savefig(OUT / "R3_common_sample_models.png",dpi=220); plt.close(fig)
print(OUT)
