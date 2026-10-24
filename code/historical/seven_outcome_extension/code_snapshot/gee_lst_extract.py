#!/usr/bin/env python3
"""MOD11A2 county LST extraction on fixed native-grid land support."""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import ee
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MONTHS = list(range(5, 11))
PERIODS = {"day": ("LST_Day_1km", "QC_Day"), "night": ("LST_Night_1km", "QC_Night")}
QA_RULES = ["strict", "relaxed"]


def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


def init_ee() -> None:
    ee.Initialize()


def overlap_days(img: ee.Image, start: ee.Date, end: ee.Date) -> ee.Number:
    left = ee.Date(ee.Number(ee.Date(img.get("system:time_start")).millis()).max(start.millis()))
    right = ee.Date(ee.Number(ee.Date(img.get("system:time_start")).advance(8, "day").millis()).min(end.millis()))
    return ee.Number(right.difference(left, "day")).max(0)


def source_windows(source: ee.ImageCollection, year: int):
    start = ee.Date.fromYMD(year, 5, 1); end = ee.Date.fromYMD(year, 11, 1)
    ic = source.filterDate(start.advance(-8, "day"), end).map(
        lambda img: img.set("season_overlap_days", overlap_days(img, start, end)))
    return ic.filter(ee.Filter.gt("season_overlap_days", 0)), start, end


def fixed_support(source: ee.ImageCollection, config: dict):
    projection = ee.Image(source.first()).select("LST_Day_1km").projection()
    projection_info = projection.getInfo()
    land250 = ee.Image(config["land_mask_product"]).select("water_mask").eq(0).unmask(0)
    # Mean aggregation creates a fixed land fraction on each native MOD11A2 grid cell.
    # This is not interpolation of a QA category.
    land_fraction = land250.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=64).reproject(projection)
    area = ee.Image.pixelArea().multiply(land_fraction).rename("fixed_support_area_m2").reproject(projection)
    return projection, projection_info, land_fraction.rename("fixed_land_fraction"), area


def qa_components(qc: ee.Image) -> dict:
    return {
        "mandatory0": qc.bitwiseAnd(3).eq(0),
        "mandatory_le1": qc.bitwiseAnd(3).lte(1),
        "data_quality0": qc.rightShift(2).bitwiseAnd(3).eq(0),
        "emissivity_error0": qc.rightShift(4).bitwiseAnd(3).eq(0),
        "lst_error0": qc.rightShift(6).bitwiseAnd(3).eq(0),
        "lst_error_le1": qc.rightShift(6).bitwiseAnd(3).lte(1),
    }


def qc_with_valid_zero_recovered(lst: ee.Image, qc_native: ee.Image) -> ee.Image:
    """Recover QC=0 masked by EE, only where the paired LST is valid.

    MOD11A2.061 specifies no fill value for QC_Day/QC_Night. Earth Engine can
    nevertheless mask value-zero QC_Night pixels. Since zero is the best QA
    code, requiring the native QC mask would delete good observations.
    """
    return qc_native.unmask(0).updateMask(lst.mask()).rename(qc_native.bandNames())


def valid_mask(img: ee.Image, period: str, rule: str, land_fraction: ee.Image) -> ee.Image:
    lst_band, qc_band = PERIODS[period]
    lst = img.select(lst_band); qc_native = img.select(qc_band)
    qc = qc_with_valid_zero_recovered(lst, qc_native); c = qa_components(qc)
    base = lst.mask().And(land_fraction.gt(0))
    if rule == "strict": condition = c["mandatory0"].And(c["data_quality0"]).And(c["lst_error0"])
    elif rule == "relaxed": condition = c["mandatory_le1"].And(c["lst_error_le1"])
    else: raise ValueError(rule)
    return base.And(condition)


def window_accumulator(img: ee.Image, period: str, rule: str, land_fraction: ee.Image,
                       support_area: ee.Image, year: int) -> ee.Image:
    lst_band, _ = PERIODS[period]; lst_c = img.select(lst_band).multiply(0.02).subtract(273.15)
    valid = valid_mask(img, period, rule, land_fraction)
    bands = []
    windows = [("season", ee.Date.fromYMD(year, 5, 1), ee.Date.fromYMD(year, 11, 1))]
    windows += [(f"m{m:02d}", ee.Date.fromYMD(year, m, 1), ee.Date.fromYMD(year, m + 1, 1)) for m in MONTHS]
    for tag, start, end in windows:
        days = overlap_days(img, start, end)
        den = support_area.updateMask(valid).multiply(days).unmask(0).rename(f"{period}_{rule}_area_days_{tag}")
        num = lst_c.multiply(support_area).updateMask(valid).multiply(days).unmask(0).rename(f"{period}_{rule}_temp_area_days_{tag}")
        bands.extend([den, num])
    return ee.Image.cat(bands)


def diagnostic_accumulator(img: ee.Image, period: str, land_fraction: ee.Image,
                           support_area: ee.Image, year: int) -> ee.Image:
    lst_band, qc_band = PERIODS[period]; lst = img.select(lst_band); qc_native = img.select(qc_band)
    qc = qc_with_valid_zero_recovered(lst, qc_native)
    c = qa_components(qc); days = overlap_days(img, ee.Date.fromYMD(year, 5, 1), ee.Date.fromYMD(year, 11, 1))
    raw_lst = lst.mask().And(land_fraction.gt(0)); raw_qc_native = qc_native.mask().And(land_fraction.gt(0))
    recovered_qc_zero = raw_lst.And(qc_native.mask().Not())
    base = raw_lst
    masks = {
        "raw_lst": raw_lst, "raw_qc_native_mask": raw_qc_native,
        "recovered_qc_zero": recovered_qc_zero, "qc_available_after_recovery": base,
        "single_mandatory0": base.And(c["mandatory0"]),
        "single_data_quality0": base.And(c["data_quality0"]),
        "single_emissivity_error0": base.And(c["emissivity_error0"]),
        "single_lst_error0": base.And(c["lst_error0"]),
        "joint_mandatory0_data_quality0": base.And(c["mandatory0"]).And(c["data_quality0"]),
        "strict_joint": base.And(c["mandatory0"]).And(c["data_quality0"]).And(c["lst_error0"]),
        "relaxed_joint": base.And(c["mandatory_le1"]).And(c["lst_error_le1"]),
    }
    return ee.Image.cat([support_area.updateMask(mask).multiply(days).unmask(0).rename(f"diag_{period}_{name}_area_days")
                         for name, mask in masks.items()])


def county_stats_expression(year: int, state_fips: list[str], config: dict, diagnostics: bool):
    source = ee.ImageCollection(config["product"]); projection, grid, land_fraction, support_area = fixed_support(source, config)
    counties = ee.FeatureCollection(config["county_product"]).filter(ee.Filter.inList("STATEFP", state_fips))
    ic, start, end = source_windows(source, year)
    summed = support_area
    for period in PERIODS:
        for rule in QA_RULES:
            summed = summed.addBands(ic.map(lambda img, p=period, q=rule:
                                             window_accumulator(ee.Image(img), p, q, land_fraction, support_area, year)).sum())
        if diagnostics:
            summed = summed.addBands(ic.map(lambda img, p=period:
                                             diagnostic_accumulator(ee.Image(img), p, land_fraction, support_area, year)).sum())
    reduced = summed.reduceRegions(collection=counties, reducer=ee.Reducer.sum(),
                                   crs=grid["crs"], crsTransform=grid["transform"], tileScale=4)
    expected_count = ic.size(); overlap_total = ic.aggregate_sum("season_overlap_days")
    return reduced.map(lambda f: ee.Feature(f).setGeometry(None).set({
        "FIPS": f.get("GEOID"), "year": year, "season_days": end.difference(start, "day"),
        "expected_image_count": expected_count, "actual_window_overlap_days": overlap_total,
        "product": config["product"], "land_mask_product": config["land_mask_product"],
        "qa_version": config["qa_version"], "spatial_support": "MOD44W land fraction aggregated to native MOD11A2 grid"
    }))


def valid_image_expression(year: int, state_fips: list[str], config: dict):
    source = ee.ImageCollection(config["product"]); projection, grid, land_fraction, support_area = fixed_support(source, config)
    counties = ee.FeatureCollection(config["county_product"]).filter(ee.Filter.inList("STATEFP", state_fips))
    ic, _, _ = source_windows(source, year); n = int(ic.size().getInfo()); images = ic.toList(n)
    bands = []
    for k in range(n):
        img = ee.Image(images.get(k)); image_id = ee.String(img.get("system:index")).getInfo()
        safe_id = image_id.replace("-", "_").replace(".", "_")
        for period in PERIODS:
            for rule in QA_RULES:
                bands.append(valid_mask(img, period, rule, land_fraction).unmask(0)
                             .rename(f"valid__{safe_id}__{period}__{rule}"))
    # One spatial aggregation for all image/rule bands avoids nested concurrent aggregations.
    fc = ee.Image.cat(bands).reduceRegions(collection=counties, reducer=ee.Reducer.max(),
                                           crs=grid["crs"], crsTransform=grid["transform"], tileScale=4)
    return fc.map(lambda f: ee.Feature(f).setGeometry(None).set({"FIPS": f.get("GEOID"), "year": year,
                                                                  "wide_validity_bands": n * 4}))


def compute_dataframe(expression, retries=3) -> pd.DataFrame:
    last = None
    for attempt in range(retries):
        try:
            return ee.data.computeFeatures({"expression": expression, "fileFormat": "PANDAS_DATAFRAME"})
        except Exception as exc:
            last = exc
            if attempt + 1 == retries: break
            time.sleep(5 * (2 ** attempt))
    raise last


def qa_histogram(config: dict, years: list[int]) -> pd.DataFrame:
    source = ee.ImageCollection(config["product"])
    counties = ee.FeatureCollection(config["county_product"]).filter(ee.Filter.inList("GEOID", config["diagnostic_counties"]))
    region = counties.geometry(); rows = []
    for year in years:
        ic, _, _ = source_windows(source, year); n = int(ic.size().getInfo())
        for k in range(n):
            img = ee.Image(ic.toList(n).get(k)); image_id = img.get("system:index").getInfo()
            for period, (lst_band, band) in PERIODS.items():
                lst = img.select(lst_band); native = img.select(band)
                recovered = qc_with_valid_zero_recovered(lst, native).rename("qc")
                hist = recovered.reduceRegion(reducer=ee.Reducer.frequencyHistogram(), geometry=region,
                    scale=1000, maxPixels=10_000_000, tileScale=4).get("qc").getInfo() or {}
                for raw, count in hist.items():
                    q = int(float(raw)); rows.append({"year": year, "image_id": image_id, "period": period,
                        "qa_value": q, "weighted_pixel_frequency": count, "mandatory": q & 3,
                        "data_quality": (q >> 2) & 3, "emissivity_error": (q >> 4) & 3,
                        "lst_error": (q >> 6) & 3, "qc_zero_recovery": "only_where_paired_LST_valid",
                        "diagnostic_scope_FIPS": ";".join(config["diagnostic_counties"])})
    return pd.DataFrame(rows)


def extract(years: list[int], states: list[str], config: dict, outdir: Path, diagnostics: bool,
            valid_counts_by_state: bool = False):
    outdir.mkdir(parents=True, exist_ok=True)
    for year in years:
        stats_path = outdir / f"lst_stats_{year}.csv"; counts_path = outdir / f"lst_valid_images_{year}.csv"
        if not stats_path.exists(): compute_dataframe(county_stats_expression(year, states, config, diagnostics)).to_csv(stats_path, index=False)
        if not counts_path.exists():
            compute_dataframe(valid_image_expression(year, states, config)).to_csv(counts_path, index=False)
    if diagnostics:
        hist_path = outdir / "qa_value_histogram.csv"
        if not hist_path.exists(): qa_histogram(config, years).to_csv(hist_path, index=False)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--years", nargs="+", type=int, required=True); ap.add_argument("--states", nargs="+", required=True)
    ap.add_argument("--output-dir", type=Path, required=True); ap.add_argument("--diagnostics", action="store_true")
    ap.add_argument("--valid-counts-by-state", action="store_true")
    args = ap.parse_args(); config = load_config(args.config); init_ee()
    extract(args.years, args.states, config, args.output_dir, args.diagnostics, args.valid_counts_by_state)


if __name__ == "__main__": main()
