#!/usr/bin/env python3
"""Convert raw fixed-support GEE exports to validated long county-year LST panels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

MONTHS = list(range(5, 11)); PERIODS = ["day", "night"]; RULES = ["strict", "relaxed"]


def norm_keys(d):
    d = d.copy(); d["FIPS"] = d.FIPS.astype(int).astype(str).str.zfill(5)
    d["STATEFP"] = d.STATEFP.astype(int).astype(str).str.zfill(2); d["year"] = d.year.astype(int)
    return d


def load_raw(indir: Path):
    stats = pd.concat([pd.read_csv(x) for x in sorted(indir.glob("lst_stats_*.csv"))], ignore_index=True)
    summaries=[]
    for path in sorted(indir.glob("lst_valid_images_*.csv")):
        if "_state" in path.stem: continue
        d=norm_keys(pd.read_csv(path))
        if "image_id" in d.columns:
            for (fips,year),g in d.groupby(["FIPS","year"]):
                for period in PERIODS:
                    for rule in RULES:
                        col=f"{period}_{rule}_valid_area_m2"
                        summaries.append({"FIPS":fips,"year":int(year),"period":period,"QA_rule":rule,
                          "valid_image_count":int(g[col].gt(0).sum()),"unique_intersecting_image_count":int(g.image_id.nunique())})
        else:
            valid_cols=[c for c in d if c.startswith("valid__")]
            for _,r in d.iterrows():
                for period in PERIODS:
                    for rule in RULES:
                        cols=[c for c in valid_cols if c.endswith(f"__{period}__{rule}")]
                        summaries.append({"FIPS":r.FIPS,"year":int(r.year),"period":period,"QA_rule":rule,
                          "valid_image_count":int(pd.to_numeric(r[cols],errors="coerce").fillna(0).gt(0).sum()),
                          "unique_intersecting_image_count":len(cols)})
    return norm_keys(stats), pd.DataFrame(summaries)


def build_panel(stats, counts):
    rows = []
    month_days = {5:31, 6:30, 7:31, 8:31, 9:30, 10:31}
    for _, r in stats.iterrows():
        D = r.fixed_support_area_m2
        for period in PERIODS:
            for rule in RULES:
                area_days = r[f"{period}_{rule}_area_days_season"]
                temp_num = r[f"{period}_{rule}_temp_area_days_season"]
                row = {"FIPS": r.FIPS, "STATEFP": r.STATEFP, "NAME": r.NAME, "year": int(r.year),
                       "period": period, "QA_rule": rule, "LST_C": temp_num / area_days if area_days > 0 else np.nan,
                       "fixed_support_area_m2": D, "valid_area_days_m2_day": area_days,
                       "coverage": area_days / (D * r.season_days),
                       "valid_equivalent_8day_periods": area_days / D / 8,
                       "expected_equivalent_8day_periods": r.season_days / 8,
                       "expected_image_count": int(r.expected_image_count),
                       "actual_window_overlap_days": r.actual_window_overlap_days,
                       "season_days": r.season_days, "ALAND_m2": r.ALAND, "AWATER_m2": r.AWATER,
                       "support_to_ALAND_ratio": D / r.ALAND, "product": r["product"],
                       "land_mask_product": r.land_mask_product, "qa_version": r.qa_version,
                       "spatial_support": r.spatial_support}
                for m in MONTHS:
                    a = r[f"{period}_{rule}_area_days_m{m:02d}"]
                    n = r[f"{period}_{rule}_temp_area_days_m{m:02d}"]
                    row[f"LST_C_m{m:02d}"] = n / a if a > 0 else np.nan
                    row[f"coverage_m{m:02d}"] = a / (D * month_days[m])
                rows.append(row)
    out = pd.DataFrame(rows)
    return out.merge(counts, on=["FIPS", "year", "period", "QA_rule"], validate="one_to_one")


def diagnostics(stats):
    rows = []
    diag_cols = [c for c in stats if c.startswith("diag_")]
    for _, r in stats.iterrows():
        denom = r.fixed_support_area_m2 * r.season_days
        for c in diag_cols:
            _, period, layer = c.split("_", 2)
            rows.append({"FIPS": r.FIPS, "STATEFP": r.STATEFP, "NAME": r.NAME, "year": int(r.year),
                         "period": period, "layer": layer.removesuffix("_area_days"),
                         "area_days_m2_day": r[c], "fixed_support_season_area_days": denom,
                         "retained_fraction": r[c] / denom})
    return pd.DataFrame(rows)


def validate(panel, expected_counties, expected_years, tol=1e-6):
    checks = []
    def add(name, ok, value, expected, severity="error"):
        checks.append({"check": name, "status": "pass" if ok else severity, "value": value, "expected": expected})
    fy = panel[["FIPS", "year"]].drop_duplicates()
    add("unique_FIPS_year", len(fy) == expected_counties * len(expected_years), len(fy), expected_counties * len(expected_years))
    add("unique_long_key", not panel.duplicated(["FIPS","year","period","QA_rule"]).any(), int(panel.duplicated(["FIPS","year","period","QA_rule"]).sum()), 0)
    add("four_rows_per_FIPS_year", panel.groupby(["FIPS","year"]).size().eq(4).all(), int(panel.groupby(["FIPS","year"]).size().min()), 4)
    add("season_days_184", panel.season_days.eq(184).all(), sorted(panel.season_days.unique().tolist()), [184])
    add("overlap_days_184", np.allclose(panel.actual_window_overlap_days,184), sorted(panel.actual_window_overlap_days.unique().tolist()), [184])
    add("expected_image_matches_unique", (panel.expected_image_count == panel.unique_intersecting_image_count).all(), int((panel.expected_image_count != panel.unique_intersecting_image_count).sum()), 0)
    add("coverage_in_0_1", ((panel.coverage >= -tol)&(panel.coverage <= 1+tol)).all(), int(((panel.coverage < -tol)|(panel.coverage > 1+tol)).sum()), 0)
    month_cols=[f"coverage_m{m:02d}" for m in MONTHS]
    add("monthly_coverage_in_0_1", ((panel[month_cols]>=-tol)&(panel[month_cols]<=1+tol)).all().all(), int(((panel[month_cols]<-tol)|(panel[month_cols]>1+tol)).sum().sum()), 0)
    w=panel.pivot(index=["FIPS","year","period"],columns="QA_rule",values="coverage")
    add("relaxed_contains_strict", (w.relaxed + tol >= w.strict).all(), int((w.relaxed + tol < w.strict).sum()), 0)
    add("valid_image_count_bound", (panel.valid_image_count <= panel.expected_image_count).all(), int((panel.valid_image_count > panel.expected_image_count).sum()), 0)
    finite=panel.LST_C.dropna(); add("LST_C_plausible", finite.between(-80,80).all(), int((~finite.between(-80,80)).sum()), 0)
    add("positive_fixed_support", panel.fixed_support_area_m2.gt(0).all(), int(panel.fixed_support_area_m2.le(0).sum()), 0)
    # Overall zero is a data-quality finding, not automatically a code failure when layer diagnostics explain it.
    for period in PERIODS:
        for rule in RULES:
            n=int(panel.query("period==@period and QA_rule==@rule").LST_C.notna().sum())
            add(f"nonmissing_{period}_{rule}", n>0, n, ">0", severity="quality_block")
    return pd.DataFrame(checks)


def inclusion_flags(panel, config):
    out=panel.copy(); months=[f"coverage_m{m:02d}" for m in MONTHS]
    for threshold in [config["coverage_rule"]["season_min"], *config["coverage_rule"]["season_sensitivity"]]:
        tag=f"{int(round(threshold*100)):03d}"
        out[f"eligible_s{tag}"]=(out.coverage>=threshold)&out[months].ge(config["coverage_rule"]["each_month_min"]).all(axis=1)&out[[f"LST_C_m{m:02d}" for m in MONTHS]].notna().all(axis=1)
    return out


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input-dir",type=Path,required=True); ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--config",type=Path,required=True); ap.add_argument("--expected-counties",type=int,required=True); ap.add_argument("--expected-years",nargs="+",type=int,required=True)
    args=ap.parse_args(); config=json.loads(args.config.read_text()); args.output_dir.mkdir(parents=True,exist_ok=True)
    stats,counts=load_raw(args.input_dir); panel=inclusion_flags(build_panel(stats,counts),config)
    diag=diagnostics(stats) if any(c.startswith("diag_") for c in stats) else pd.DataFrame()
    checks=validate(panel,args.expected_counties,args.expected_years,config["coverage_tolerance"])
    panel.to_csv(args.output_dir/"county_year_LST_long.csv",index=False); checks.to_csv(args.output_dir/"validation_checks.csv",index=False)
    if len(diag): diag.to_csv(args.output_dir/"QA_layer_diagnostics.csv",index=False)
    summary=panel.groupby(["STATEFP","year","period","QA_rule"],as_index=False).agg(
        n_counties=("FIPS","nunique"),n_valid_LST=("LST_C",lambda x:x.notna().sum()),coverage_mean=("coverage","mean"),
        coverage_min=("coverage","min"),coverage_median=("coverage","median"),coverage_max=("coverage","max"),
        valid_image_count_mean=("valid_image_count","mean"),expected_image_count=("expected_image_count","first"),
        n_eligible_main=("eligible_s070","sum"))
    summary.to_csv(args.output_dir/"coverage_summary.csv",index=False)
    print(json.dumps({"rows":len(panel),"unique_FIPS_year":len(panel[["FIPS","year"]].drop_duplicates()),
                      "errors":int(checks.status.eq("error").sum()),"quality_blocks":int(checks.status.eq("quality_block").sum())},indent=2))


if __name__=="__main__": main()
