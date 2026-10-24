from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from docx import Document


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_data_root() -> Path:
    required = {"PM2.5", "health", "fire", "ecnomy"}

    def is_data_root(path: Path) -> bool:
        return path.exists() and path.is_dir() and required.issubset({p.name for p in path.iterdir() if p.is_dir()})

    env_path = os.environ.get("AFIRE_DATA_ROOT")
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend([
        PROJECT_ROOT.parent,
        PROJECT_ROOT.parent / "Afire",
        PROJECT_ROOT / "Afire",
        Path(r"D:\postgraduate\wildfire\Afire"),
    ])
    for candidate in candidates:
        if is_data_root(candidate):
            return candidate
    tried = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "Raw data folder was not found. Set AFIRE_DATA_ROOT to the folder that contains "
        "`PM2.5`, `health`, `fire`, and `ecnomy`.\n\nTried:\n" + tried
    )


DATA_ROOT = resolve_data_root()

DIRS = {
    "processed": PROJECT_ROOT / "data_processed",
    "results": PROJECT_ROOT / "results",
    "figures": PROJECT_ROOT / "figures",
    "tables": PROJECT_ROOT / "tables",
    "reports": PROJECT_ROOT / "reports",
    "logs": PROJECT_ROOT / "logs",
}


STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
ABBR_STATE = {v: k for k, v in STATE_ABBR.items()}
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}
FIPS_ABBR = {v: k for k, v in STATE_FIPS.items()}


STATE_TILE = {
    "AK": (0, 0), "ME": (10, 0),
    "VT": (9, 1), "NH": (10, 1), "WA": (0, 2), "ID": (1, 2), "MT": (2, 2),
    "ND": (3, 2), "MN": (4, 2), "IL": (5, 2), "WI": (6, 2), "MI": (7, 2),
    "NY": (8, 2), "MA": (9, 2), "RI": (10, 2),
    "OR": (0, 3), "NV": (1, 3), "WY": (2, 3), "SD": (3, 3), "IA": (4, 3),
    "IN": (5, 3), "OH": (6, 3), "PA": (7, 3), "NJ": (8, 3), "CT": (9, 3),
    "CA": (0, 4), "UT": (1, 4), "CO": (2, 4), "NE": (3, 4), "MO": (4, 4),
    "KY": (5, 4), "WV": (6, 4), "VA": (7, 4), "MD": (8, 4), "DE": (9, 4),
    "AZ": (1, 5), "NM": (2, 5), "KS": (3, 5), "AR": (4, 5), "TN": (5, 5),
    "NC": (6, 5), "SC": (7, 5), "DC": (8, 5),
    "OK": (3, 6), "LA": (4, 6), "MS": (5, 6), "AL": (6, 6), "GA": (7, 6),
    "HI": (0, 7), "TX": (3, 7), "FL": (8, 7),
}


def ensure_dirs() -> None:
    for path in DIRS.values():
        path.mkdir(parents=True, exist_ok=True)
    for sub in ["annual_exposure_tile_maps", "annual_health_tile_maps", "wphii_tile_maps"]:
        (DIRS["figures"] / sub).mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ensure_dirs()
    with (DIRS["logs"] / "pipeline.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")


def clean_number(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if not s or s.lower() in {"unreliable", "suppressed", "nan", "not applicable"}:
        return np.nan
    m = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", s)
    if not m:
        return np.nan
    return float(m.group(0).replace(",", ""))


def read_csv_flexible(path_or_buffer, **kwargs) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1", "utf-16"]
    last_exc = None
    for enc in encodings:
        try:
            return pd.read_csv(path_or_buffer, encoding=enc, **kwargs)
        except UnicodeDecodeError as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    return pd.read_csv(path_or_buffer, **kwargs)


def state_from_cdc(value: str) -> tuple[str, str, str]:
    s = str(value)
    m = re.match(r"^(.*?)\s*\((\d{2})\)", s)
    if m:
        name = m.group(1).strip()
        fips = m.group(2)
    else:
        name = s.strip()
        fips = STATE_FIPS.get(STATE_ABBR.get(name, ""), "")
    abbr = FIPS_ABBR.get(fips, STATE_ABBR.get(name, ""))
    return name, abbr, fips


def year_to_period(year: int) -> str:
    if year <= 2010:
        return "2006_2010"
    if year <= 2015:
        return "2011_2015"
    return "2016_2020"


def minmax(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def weighted_mean(x: pd.Series, w: pd.Series) -> float:
    x = pd.to_numeric(x, errors="coerce")
    w = pd.to_numeric(w, errors="coerce")
    mask = x.notna() & w.notna() & (w > 0)
    if not mask.any():
        return float(x.mean())
    return float(np.average(x[mask], weights=w[mask]))


def weighted_linear_fit(x, y, w=None):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if w is None:
        w = np.ones_like(y)
    else:
        w = np.asarray(w, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    if mask.sum() < 3:
        return np.nan, np.nan
    X = np.column_stack([np.ones(mask.sum()), x[mask]])
    sw = np.sqrt(w[mask])
    beta = np.linalg.pinv(X.T @ (sw[:, None] * sw[:, None] * X)) @ (X.T @ (w[mask] * y[mask]))
    return float(beta[0]), float(beta[1])


def gini(values, weights=None) -> float:
    x = np.asarray(values, dtype=float)
    if weights is None:
        weights = np.ones_like(x)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0) & (x >= 0)
    x, w = x[mask], w[mask]
    if len(x) < 2 or np.sum(x * w) == 0:
        return np.nan
    order = np.argsort(x)
    x, w = x[order], w[order]
    cw = np.cumsum(w)
    cxw = np.cumsum(x * w)
    rel_w = cw / cw[-1]
    rel_xw = cxw / cxw[-1]
    return float(1 - 2 * np.trapz(rel_xw, rel_w))


def theil(values, weights=None) -> float:
    x = np.asarray(values, dtype=float)
    if weights is None:
        weights = np.ones_like(x)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0) & (x > 0)
    x, w = x[mask], w[mask]
    if len(x) < 2:
        return np.nan
    mu = np.average(x, weights=w)
    if mu <= 0:
        return np.nan
    ratio = x / mu
    return float(np.average(ratio * np.log(ratio), weights=w))


def concentration_index(values, rankvar, weights=None) -> float:
    y = np.asarray(values, dtype=float)
    r = np.asarray(rankvar, dtype=float)
    if weights is None:
        weights = np.ones_like(y)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(y) & np.isfinite(r) & np.isfinite(w) & (w > 0)
    y, r, w = y[mask], r[mask], w[mask]
    if len(y) < 3 or np.average(y, weights=w) == 0:
        return np.nan
    order = np.argsort(r)
    y, w = y[order], w[order]
    cw = np.cumsum(w)
    ridit = (cw - 0.5 * w) / cw[-1]
    mu = np.average(y, weights=w)
    cov = np.average((y - mu) * (ridit - np.average(ridit, weights=w)), weights=w)
    return float(2 * cov / mu)


def color_ramp(value: float, lo_color=(242, 245, 247), hi_color=(179, 42, 37)):
    v = 0 if pd.isna(value) else max(0, min(1, float(value)))
    return tuple(int(lo_color[i] + v * (hi_color[i] - lo_color[i])) for i in range(3))


def get_font(size=18):
    for name in ["arial.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/msyh.ttc"]:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_tile_map(df: pd.DataFrame, value_col: str, title: str, out: Path, label_col="state_abbr"):
    data = df[[label_col, value_col]].dropna(subset=[label_col]).copy()
    vals = pd.to_numeric(data[value_col], errors="coerce")
    lo, hi = vals.quantile(0.02), vals.quantile(0.98)
    if pd.isna(lo) or pd.isna(hi) or lo == hi:
        lo, hi = vals.min(), vals.max()
    width, height = 980, 760
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    title_font = get_font(28)
    label_font = get_font(18)
    small_font = get_font(14)
    d.text((30, 20), title, fill=(20, 24, 28), font=title_font)
    tile = 72
    gap = 8
    x0, y0 = 30, 85
    value_by_state = dict(zip(data[label_col], vals))
    for abbr, (col, row) in STATE_TILE.items():
        x, y = x0 + col * (tile + gap), y0 + row * (tile + gap)
        raw = value_by_state.get(abbr, np.nan)
        norm = np.nan if pd.isna(raw) else (raw - lo) / (hi - lo) if hi != lo else 0
        fill = color_ramp(norm)
        d.rounded_rectangle((x, y, x + tile, y + tile), radius=8, fill=fill, outline=(210, 210, 210))
        txt_fill = (255, 255, 255) if not pd.isna(norm) and norm > 0.55 else (20, 24, 28)
        d.text((x + 10, y + 8), abbr, fill=txt_fill, font=label_font)
        if not pd.isna(raw):
            d.text((x + 9, y + 40), f"{raw:.2g}", fill=txt_fill, font=small_font)
    legend_x, legend_y = 30, height - 70
    for i in range(220):
        c = color_ramp(i / 219)
        d.line((legend_x + i, legend_y, legend_x + i, legend_y + 18), fill=c)
    d.rectangle((legend_x, legend_y, legend_x + 220, legend_y + 18), outline=(120, 120, 120))
    d.text((legend_x, legend_y + 25), f"low {lo:.2g}", fill=(40, 44, 50), font=small_font)
    d.text((legend_x + 150, legend_y + 25), f"high {hi:.2g}", fill=(40, 44, 50), font=small_font)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def draw_line_chart(df: pd.DataFrame, x_col: str, y_cols: list[str], title: str, out: Path):
    plot = df[[x_col] + y_cols].copy()
    width, height = 1100, 680
    margin = 80
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    title_font = get_font(28)
    font = get_font(16)
    d.text((35, 25), title, fill=(20, 24, 28), font=title_font)
    x = pd.to_numeric(plot[x_col], errors="coerce")
    y_all = pd.concat([pd.to_numeric(plot[c], errors="coerce") for c in y_cols])
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y_all.min()), float(y_all.max())
    if ymin == ymax:
        ymin, ymax = ymin - 1, ymax + 1
    x1, y1 = margin, height - margin
    x2, y2 = width - margin, margin + 30
    d.line((x1, y1, x2, y1), fill=(80, 80, 80), width=2)
    d.line((x1, y1, x1, y2), fill=(80, 80, 80), width=2)
    colors = [(33, 113, 181), (203, 24, 29), (35, 139, 69), (117, 107, 177), (230, 85, 13)]
    def sx(v): return x1 + (float(v) - xmin) / (xmax - xmin) * (x2 - x1) if xmax != xmin else (x1 + x2) / 2
    def sy(v): return y1 - (float(v) - ymin) / (ymax - ymin) * (y1 - y2)
    for i in range(6):
        yy = y1 - i / 5 * (y1 - y2)
        val = ymin + i / 5 * (ymax - ymin)
        d.line((x1, yy, x2, yy), fill=(235, 238, 240))
        d.text((20, yy - 8), f"{val:.2g}", fill=(60, 60, 60), font=font)
    years = sorted(x.dropna().unique())
    for yr in years[::max(1, len(years)//8)]:
        xx = sx(yr)
        d.text((xx - 18, y1 + 10), str(int(yr)), fill=(60, 60, 60), font=font)
    for idx, col in enumerate(y_cols):
        color = colors[idx % len(colors)]
        pts = []
        for _, row in plot.sort_values(x_col).iterrows():
            if pd.notna(row[x_col]) and pd.notna(row[col]):
                pts.append((sx(row[x_col]), sy(row[col])))
        if len(pts) >= 2:
            d.line(pts, fill=color, width=4)
            for p in pts:
                d.ellipse((p[0]-3, p[1]-3, p[0]+3, p[1]+3), fill=color)
        d.rectangle((width - margin - 250, margin + idx * 28, width - margin - 235, margin + idx * 28 + 15), fill=color)
        d.text((width - margin - 225, margin + idx * 28 - 2), col[:28], fill=(30, 30, 30), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def draw_bar_chart(df: pd.DataFrame, label_col: str, value_col: str, title: str, out: Path, top_n=20):
    plot = df[[label_col, value_col]].dropna().sort_values(value_col, ascending=False).head(top_n)
    width, height = 1100, 760
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    title_font = get_font(28)
    font = get_font(15)
    d.text((35, 25), title, fill=(20, 24, 28), font=title_font)
    x0, y0 = 260, 90
    bar_h, gap = 24, 9
    maxv = pd.to_numeric(plot[value_col], errors="coerce").max()
    for i, (_, row) in enumerate(plot.iterrows()):
        y = y0 + i * (bar_h + gap)
        v = float(row[value_col])
        w = 760 * v / maxv if maxv else 0
        d.text((35, y + 2), str(row[label_col])[:27], fill=(35, 35, 35), font=font)
        d.rectangle((x0, y, x0 + w, y + bar_h), fill=(203, 82, 67))
        d.text((x0 + w + 8, y + 2), f"{v:.3g}", fill=(35, 35, 35), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def draw_heatmap(df: pd.DataFrame, row_col: str, col_col: str, value_col: str, title: str, out: Path):
    piv = df.pivot_table(index=row_col, columns=col_col, values=value_col, aggfunc="mean")
    rows, cols = list(piv.index), list(piv.columns)
    cell_w, cell_h = 70, 32
    left, top = 260, 90
    width = left + cell_w * max(1, len(cols)) + 80
    height = top + cell_h * max(1, len(rows)) + 90
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    title_font = get_font(26)
    font = get_font(13)
    d.text((35, 25), title, fill=(20, 24, 28), font=title_font)
    vals = piv.values.flatten()
    vals = vals[np.isfinite(vals)]
    lo, hi = (np.nan, np.nan) if len(vals) == 0 else (np.nanpercentile(vals, 2), np.nanpercentile(vals, 98))
    if not np.isfinite(lo) or lo == hi:
        lo, hi = (np.nanmin(vals) if len(vals) else 0, np.nanmax(vals) if len(vals) else 1)
    for j, c in enumerate(cols):
        d.text((left + j * cell_w + 6, top - 24), str(c), fill=(35, 35, 35), font=font)
    for i, r in enumerate(rows):
        d.text((35, top + i * cell_h + 8), str(r)[:32], fill=(35, 35, 35), font=font)
        for j, c in enumerate(cols):
            raw = piv.loc[r, c]
            norm = (raw - lo) / (hi - lo) if pd.notna(raw) and hi != lo else np.nan
            fill = color_ramp(norm, (245, 247, 250), (42, 93, 176))
            x, y = left + j * cell_w, top + i * cell_h
            d.rectangle((x, y, x + cell_w - 2, y + cell_h - 2), fill=fill, outline=(230, 230, 230))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def df_to_markdown(df: pd.DataFrame, max_rows: int | None = None) -> str:
    d = df.copy()
    if max_rows is not None:
        d = d.head(max_rows)
    d = d.fillna("")
    cols = list(d.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |"]
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for _, row in d.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                vals.append(f"{v:.4g}")
            else:
                vals.append(str(v).replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def scan_data() -> pd.DataFrame:
    ensure_dirs()
    rows = []
    for path in DATA_ROOT.rglob("*"):
        parts_lower = {p.lower() for p in path.parts}
        if (
            not path.is_file()
            or ".cdc_wonder_browser_profile" in str(path)
            or any(p.startswith("afire_project") for p in parts_lower)
        ):
            continue
        rec = {
            "path": str(path),
            "relative_path": str(path.relative_to(DATA_ROOT)),
            "extension": path.suffix.lower(),
            "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
            "columns": "",
            "n_columns": np.nan,
            "sample_rows": np.nan,
            "year_min": np.nan,
            "year_max": np.nan,
            "notes": "",
        }
        try:
            if path.suffix.lower() == ".csv":
                sample = read_csv_flexible(path, nrows=200)
                rec["columns"] = " | ".join(map(str, sample.columns))
                rec["n_columns"] = len(sample.columns)
                rec["sample_rows"] = len(sample)
                ycols = [c for c in sample.columns if "year" in c.lower() or c.lower() == "date"]
                yrs = []
                for c in ycols:
                    vals = sample[c].astype(str).str.extract(r"(\d{4})")[0]
                    yrs.extend(pd.to_numeric(vals, errors="coerce").dropna().astype(int).tolist())
                if yrs:
                    rec["year_min"] = min(yrs)
                    rec["year_max"] = max(yrs)
            elif path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path) as zf:
                    rec["columns"] = " | ".join(zf.namelist())
                    rec["n_columns"] = len(zf.namelist())
                    for name in zf.namelist():
                        if name.lower().endswith(".csv"):
                            with zf.open(name) as f:
                                sample = read_csv_flexible(f, nrows=200)
                            rec["notes"] = f"csv inside: {name}; columns: {' | '.join(map(str, sample.columns))}"
                            break
            else:
                rec["notes"] = "not tabular-scanned"
        except Exception as exc:
            rec["notes"] = f"scan_error: {exc}"
        rows.append(rec)
    out = pd.DataFrame(rows).sort_values(["extension", "relative_path"])
    out.to_csv(DIRS["tables"] / "data_inventory.csv", index=False, encoding="utf-8-sig")
    return out


def build_pm25_state_year() -> pd.DataFrame:
    state_path = DIRS["processed"] / "state_year_exposure.csv"
    county_path = DIRS["processed"] / "county_year_smoke_pm25.csv"
    if state_path.exists():
        state = pd.read_csv(state_path, dtype={"state_fips": str})
        state.to_csv(DIRS["tables"] / "state_year_exposure.csv", index=False, encoding="utf-8-sig")
        return state
    path = DATA_ROOT / "PM2.5" / "smokePM2pt5_predictions_daily_county_20060101-20201231.csv"
    if county_path.exists():
        county_year = pd.read_csv(county_path, dtype={"GEOID": str, "state_fips": str})
    else:
        use = ["GEOID", "date", "smokePM_pred"]
        chunks = []
        for chunk in pd.read_csv(path, dtype={"GEOID": str}, usecols=use, chunksize=750_000):
            chunk["GEOID"] = chunk["GEOID"].str.zfill(5)
            chunk["state_fips"] = chunk["GEOID"].str[:2]
            chunk["state_abbr"] = chunk["state_fips"].map(FIPS_ABBR)
            chunk["state"] = chunk["state_abbr"].map(ABBR_STATE)
            chunk["year"] = pd.to_numeric(chunk["date"].astype(str).str[:4], errors="coerce").astype("Int64")
            chunk["smokePM_pred"] = pd.to_numeric(chunk["smokePM_pred"], errors="coerce")
            g = chunk.dropna(subset=["state", "year"]).groupby(["state_fips", "state_abbr", "state", "GEOID", "year"]).agg(
                county_smoke_pm25_sum=("smokePM_pred", "sum"),
                county_smoke_pm25_mean_smoke_days=("smokePM_pred", "mean"),
                county_smoke_days=("smokePM_pred", "count"),
                county_smoke_pm25_max=("smokePM_pred", "max"),
            ).reset_index()
            chunks.append(g)
        county_year = pd.concat(chunks, ignore_index=True).groupby(
            ["state_fips", "state_abbr", "state", "GEOID", "year"], as_index=False
        ).sum(numeric_only=True)
        county_year["county_smoke_pm25_annual_burden"] = county_year["county_smoke_pm25_sum"] / 365.25
        county_year.to_csv(county_path, index=False, encoding="utf-8-sig")

    ses = load_ses_county_year()
    county_year = county_year.merge(ses[["GEOID", "year", "total_population"]], on=["GEOID", "year"], how="left")
    state_rows = []
    for keys, sub in county_year.groupby(["state_fips", "state_abbr", "state", "year"]):
        row = dict(zip(["state_fips", "state_abbr", "state", "year"], keys))
        row["smoke_pm25_annual_burden"] = weighted_mean(sub["county_smoke_pm25_annual_burden"], sub["total_population"])
        row["smoke_pm25_mean_smoke_days"] = weighted_mean(sub["county_smoke_pm25_mean_smoke_days"], sub["total_population"])
        row["smoke_days_mean"] = weighted_mean(sub["county_smoke_days"], sub["total_population"])
        row["smoke_pm25_max_county_day"] = sub["county_smoke_pm25_max"].max()
        row["n_counties_with_smoke"] = sub["GEOID"].nunique()
        row["population_observed"] = pd.to_numeric(sub["total_population"], errors="coerce").sum()
        state_rows.append(row)
    state = pd.DataFrame(state_rows)
    state.to_csv(DIRS["processed"] / "state_year_exposure.csv", index=False, encoding="utf-8-sig")
    state.to_csv(DIRS["tables"] / "state_year_exposure.csv", index=False, encoding="utf-8-sig")
    return state


def load_ses_county_year() -> pd.DataFrame:
    cache = DIRS["processed"] / "county_year_ses.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype={"GEOID": str, "state_fips": str, "county_fips": str, "STATEA": str})
    path = DATA_ROOT / "ecnomy" / "NHGIS_SES_simplified" / "ses_county_period_simplified.csv"
    ses = pd.read_csv(path, dtype={"county_fips": str, "STATEA": str})
    ses["GEOID"] = ses["county_fips"].astype(str).str.zfill(5)
    ses["state_fips"] = ses["STATEA"].astype(str).str.zfill(2)
    ses["state_abbr"] = ses["state_fips"].map(FIPS_ABBR).fillna(ses["STUSAB"])
    ses["state"] = ses["state_abbr"].map(ABBR_STATE)
    parts = []
    for year in range(2006, 2021):
        desired_start = min(year, 2016)
        sub = ses[pd.to_numeric(ses["period_start"], errors="coerce").eq(desired_start)].copy()
        sub["year"] = year
        parts.append(sub)
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(cache, index=False, encoding="utf-8-sig")
    return out


def build_ses_state_year() -> pd.DataFrame:
    cache = DIRS["processed"] / "state_year_ses.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype={"state_fips": str})
    ses = load_ses_county_year()
    vars_mean = [
        "median_household_income", "per_capita_income", "poverty_rate", "unemployment_rate",
        "less_than_hs_rate", "bachelor_plus_rate", "nonwhite_rate", "hispanic_rate",
        "foreign_born_rate", "limited_english_rate", "renter_rate", "no_vehicle_rate",
        "rent_burden_30plus_rate", "overcrowding_rate", "low_income_under_30k_rate",
        "ses_disadvantage_z",
    ]
    rows = []
    for keys, sub in ses.groupby(["state_fips", "state_abbr", "state", "year"]):
        row = dict(zip(["state_fips", "state_abbr", "state", "year"], keys))
        row["total_population"] = pd.to_numeric(sub["total_population"], errors="coerce").sum()
        for c in vars_mean:
            if c in sub:
                row[c] = weighted_mean(sub[c], sub["total_population"])
        rows.append(row)
    state = pd.DataFrame(rows)
    state.to_csv(DIRS["processed"] / "state_year_ses.csv", index=False, encoding="utf-8-sig")
    return state


def load_cdc_health() -> pd.DataFrame:
    path = DATA_ROOT / "health" / "cdc_wonder_state_year_output" / "cdc_wonder_all_7_causes_state_year_2006_2020.csv"
    raw = pd.read_csv(path)
    colmap = {}
    for c in raw.columns:
        lc = c.lower()
        if c in {"cause_id", "cause_en", "cause_zh", "icd10_range"}:
            colmap[c] = c
        elif "state_state" in lc:
            colmap[c] = "state_raw"
        elif lc.startswith("year_") or c == "Year":
            colmap[c] = "year"
        elif lc.startswith("deaths_") or c == "Deaths":
            colmap[c] = "deaths"
        elif lc.startswith("population_") or c == "Population":
            colmap[c] = "population"
        elif "crude rate" in lc:
            colmap[c] = "crude_rate_per_100k"
        elif "age adjusted rate per 100,000" in lc:
            colmap[c] = "age_adjusted_rate_raw"
        elif "standard error" in lc:
            colmap[c] = "age_adjusted_rate_se"
    h = raw.rename(columns=colmap)
    states = h["state_raw"].apply(state_from_cdc)
    h["state"] = [x[0] for x in states]
    h["state_abbr"] = [x[1] for x in states]
    h["state_fips"] = [x[2] for x in states]
    h["year"] = pd.to_numeric(h["year"], errors="coerce").astype("Int64")
    h["deaths"] = h["deaths"].apply(clean_number)
    h["population"] = h["population"].apply(clean_number)
    h["crude_rate_per_100k"] = h["crude_rate_per_100k"].apply(clean_number)
    h["age_adjusted_rate_per_100k"] = h["age_adjusted_rate_raw"].apply(clean_number)
    h["age_adjusted_rate_se"] = h["age_adjusted_rate_se"].apply(clean_number)
    keep = [
        "cause_id", "cause_en", "cause_zh", "icd10_range", "state", "state_abbr", "state_fips",
        "year", "deaths", "population", "crude_rate_per_100k", "age_adjusted_rate_per_100k",
        "age_adjusted_rate_se",
    ]
    h = h[keep].dropna(subset=["state_abbr", "year"])
    h.to_csv(DIRS["processed"] / "state_year_health_by_disease.csv", index=False, encoding="utf-8-sig")
    h.to_csv(DIRS["tables"] / "state_year_health_by_disease.csv", index=False, encoding="utf-8-sig")
    return h


def scan_other_health() -> pd.DataFrame:
    rows = []
    brfss_path = DATA_ROOT / "health" / "brfss.csv"
    if brfss_path.exists():
        try:
            b = read_csv_flexible(brfss_path)
        except pd.errors.ParserError:
            b = read_csv_flexible(brfss_path, engine="python", on_bad_lines="skip")
            log("BRFSS supplement read with on_bad_lines=skip because of irregular rows")
        brfss_year = pd.to_numeric(b["year"], errors="coerce") if "year" in b else pd.Series(dtype=float)
        brfss_year_text = ""
        if brfss_year.notna().any():
            brfss_year_text = f"{int(brfss_year.min())}-{int(brfss_year.max())}"
        rows.append({
            "dataset": "BRFSS asthma",
            "rows": len(b),
            "years": brfss_year_text,
            "geo_level": ", ".join(sorted(map(str, b.get("geo_level", pd.Series()).dropna().unique()))[:6]),
            "health_categories": ", ".join(sorted(map(str, b.get("measure", pd.Series()).dropna().unique()))[:20]),
            "use_in_main_analysis": "supplemental scan only; CDC WONDER mortality used for main disease-specific models",
        })
        state_total = b[(b.get("geo_level") == "state") & (b.get("group_type") == "total")].copy()
        if not state_total.empty:
            state_total.to_csv(DIRS["processed"] / "brfss_state_year_supplement.csv", index=False, encoding="utf-8-sig")
    for zip_name in ["COPD.zip", "GBD.zip"]:
        path = DATA_ROOT / "health" / zip_name
        if path.exists():
            with zipfile.ZipFile(path) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                note = ""
                years = ""
                cats = ""
                rows_n = np.nan
                if csv_names:
                    with zf.open(csv_names[0]) as f:
                        d = read_csv_flexible(f)
                    rows_n = len(d)
                    ycol = "Year" if "Year" in d.columns else "year" if "year" in d.columns else None
                    if ycol:
                        years = f"{pd.to_numeric(d[ycol], errors='coerce').min():.0f}-{pd.to_numeric(d[ycol], errors='coerce').max():.0f}"
                    for c in ["cause_name", "measure", "measure_name"]:
                        if c in d.columns:
                            cats = ", ".join(sorted(map(str, d[c].dropna().unique()))[:20])
                            break
                    note = "columns: " + " | ".join(map(str, d.columns))
                rows.append({
                    "dataset": zip_name,
                    "rows": rows_n,
                    "years": years,
                    "geo_level": "state-like" if zip_name == "COPD.zip" else "GBD locations",
                    "health_categories": cats,
                    "use_in_main_analysis": f"supplemental inventory; {note}",
                })
    out = pd.DataFrame(rows)
    out.to_csv(DIRS["tables"] / "other_health_data_inventory.csv", index=False, encoding="utf-8-sig")
    return out


def build_fire_state_year(exposure: pd.DataFrame) -> pd.DataFrame:
    fire_path = DATA_ROOT / "fire" / "interagency_top100_fire_state_county_city_summary.csv"
    fire = pd.read_csv(fire_path)
    rows = []
    for _, r in fire.iterrows():
        year = int(r["FIRE_YEAR_INT"]) if pd.notna(r.get("FIRE_YEAR_INT")) else np.nan
        acres = clean_number(r.get("GIS_ACRES", r.get("SizeMetricAcres")))
        states = []
        if pd.notna(r.get("intersect_states")):
            states.extend([s.strip() for s in str(r["intersect_states"]).split(";") if s.strip()])
        elif pd.notna(r.get("centroid_state")):
            states.append(str(r["centroid_state"]).strip())
        states = sorted(set(states))
        share = acres / len(states) if states and pd.notna(acres) else np.nan
        for state in states:
            abbr = STATE_ABBR.get(state)
            if not abbr:
                continue
            rows.append({
                "state": state,
                "state_abbr": abbr,
                "state_fips": STATE_FIPS.get(abbr),
                "year": year,
                "top100_fire_count": 1,
                "top100_burned_acres_allocated": share,
                "top100_burned_acres_total_fire": acres,
            })
    if rows:
        out = pd.DataFrame(rows).groupby(["state", "state_abbr", "state_fips", "year"], as_index=False).agg(
            top100_fire_count=("top100_fire_count", "sum"),
            top100_burned_acres_allocated=("top100_burned_acres_allocated", "sum"),
            top100_burned_acres_total_fire=("top100_burned_acres_total_fire", "sum"),
        )
    else:
        out = pd.DataFrame(columns=["state", "state_abbr", "state_fips", "year", "top100_fire_count", "top100_burned_acres_allocated"])
    base = exposure[["state", "state_abbr", "state_fips", "year", "smoke_pm25_annual_burden", "smoke_days_mean"]].copy()
    out = base.merge(out, on=["state", "state_abbr", "state_fips", "year"], how="left")
    for c in ["top100_fire_count", "top100_burned_acres_allocated", "top100_burned_acres_total_fire"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    out["fire_covered_smoke_gt0"] = (out["smoke_pm25_annual_burden"] > 0).astype(int)
    out["pm25_cover_top25"] = 0
    out["pm25_cover_top10"] = 0
    for year, sub in out.groupby("year"):
        q = sub["smoke_pm25_annual_burden"].quantile(0.75)
        q90 = sub["smoke_pm25_annual_burden"].quantile(0.90)
        out.loc[sub.index, "pm25_cover_top25"] = (sub["smoke_pm25_annual_burden"] >= q).astype(int)
        out.loc[sub.index, "pm25_cover_top10"] = (sub["smoke_pm25_annual_burden"] >= q90).astype(int)
    out["top100_fire_any"] = (out["top100_burned_acres_allocated"] > 0).astype(int)
    out["top100_fire_pm25_any"] = ((out["top100_fire_any"] == 1) & (out["fire_covered_smoke_gt0"] == 1)).astype(int)
    out["top100_fire_pm25_cover"] = ((out["top100_fire_any"] == 1) & (out["pm25_cover_top25"] == 1)).astype(int)
    out["top100_fire_pm25_cover_top10"] = ((out["top100_fire_any"] == 1) & (out["pm25_cover_top10"] == 1)).astype(int)
    out["fire_pm25_alignment_class"] = (
        out["top100_fire_any"].astype(int) * 2 + out["pm25_cover_top25"].astype(int)
    )
    out["fire_pm25_alignment_label"] = out["fire_pm25_alignment_class"].map({
        0: "neither_top100_fire_nor_top25_pm25",
        1: "top25_pm25_without_top100_fire",
        2: "top100_fire_without_top25_pm25",
        3: "top100_fire_and_top25_pm25",
    })
    out["top100_burned_acres_log1p"] = np.log1p(out["top100_burned_acres_allocated"])
    out["pm25_norm_by_year"] = out.groupby("year")["smoke_pm25_annual_burden"].transform(minmax)
    out["top100_acres_norm_by_year"] = out.groupby("year")["top100_burned_acres_log1p"].transform(minmax)
    out["fire_pm25_cover_intensity"] = out["pm25_norm_by_year"] * out["top100_acres_norm_by_year"]
    out["fire_covered"] = out["top100_fire_pm25_cover"]
    out["fire_covered_definition"] = "v2: top100_fire_any == 1 and annual smoke PM2.5 in top 25% within year"
    out.to_csv(DIRS["processed"] / "fire_covered_state_year.csv", index=False, encoding="utf-8-sig")
    out.to_csv(DIRS["tables"] / "fire_covered_state_year.csv", index=False, encoding="utf-8-sig")
    out.to_csv(DIRS["tables"] / "top100_fire_pm25_cover_state_year.csv", index=False, encoding="utf-8-sig")
    return out


def build_panel() -> pd.DataFrame:
    exposure = build_pm25_state_year()
    ses = build_ses_state_year()
    fire = build_fire_state_year(exposure)
    health = load_cdc_health()
    panel = health.merge(exposure, on=["state", "state_abbr", "state_fips", "year"], how="left")
    panel = panel.merge(ses, on=["state", "state_abbr", "state_fips", "year"], how="left", suffixes=("", "_ses"))
    panel = panel.merge(
        fire[["state", "state_abbr", "state_fips", "year", "fire_covered", "fire_covered_definition",
              "pm25_cover_top25", "pm25_cover_top10", "top100_fire_any", "top100_fire_pm25_any",
              "top100_fire_pm25_cover", "top100_fire_pm25_cover_top10", "fire_pm25_alignment_class",
              "fire_pm25_alignment_label", "fire_pm25_cover_intensity", "top100_fire_count",
              "top100_burned_acres_allocated"]],
        on=["state", "state_abbr", "state_fips", "year"], how="left"
    )
    panel["health_population"] = panel["population"]
    panel["population"] = panel["population"].fillna(panel.get("total_population"))
    for c in ["fire_covered", "pm25_cover_top25", "pm25_cover_top10", "top100_fire_any",
              "top100_fire_pm25_any", "top100_fire_pm25_cover", "top100_fire_pm25_cover_top10",
              "fire_pm25_cover_intensity", "top100_fire_count", "top100_burned_acres_allocated"]:
        panel[c] = pd.to_numeric(panel[c], errors="coerce").fillna(0)
    panel["year_centered"] = panel["year"].astype(float) - panel["year"].astype(float).mean()
    panel.to_csv(DIRS["processed"] / "state_year_disease_panel.csv", index=False, encoding="utf-8-sig")
    return panel


def missing_report(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in panel.columns:
        rows.append({
            "column": col,
            "missing_n": int(panel[col].isna().sum()),
            "missing_pct": float(panel[col].isna().mean()),
            "nonmissing_n": int(panel[col].notna().sum()),
        })
    out = pd.DataFrame(rows).sort_values("missing_pct", ascending=False)
    out.to_csv(DIRS["tables"] / "missing_data_report.csv", index=False, encoding="utf-8-sig")
    return out


def annual_analysis(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    exp = panel.drop_duplicates(["state_abbr", "year"]).copy()
    rows = []
    for year, sub in exp.groupby("year"):
        pop = pd.to_numeric(sub["population"], errors="coerce")
        vuln = pd.to_numeric(sub["ses_disadvantage_z"], errors="coerce")
        exposure = pd.to_numeric(sub["smoke_pm25_annual_burden"], errors="coerce")
        high = sub[vuln >= vuln.median()]
        low = sub[vuln < vuln.median()]
        _, sii = weighted_linear_fit(vuln, exposure, pop)
        rows.append({
            "year": int(year),
            "n_states": sub["state_abbr"].nunique(),
            "population_weighted_smoke_pm25": weighted_mean(exposure, pop),
            "mean_smoke_pm25": float(exposure.mean()),
            "median_smoke_pm25": float(exposure.median()),
            "gini_smoke_pm25": gini(exposure, pop),
            "theil_smoke_pm25": theil(exposure, pop),
            "concentration_index_by_ses_disadvantage": concentration_index(exposure, vuln, pop),
            "sii_by_ses_disadvantage": sii,
            "rii_by_ses_disadvantage": sii / weighted_mean(exposure, pop) if weighted_mean(exposure, pop) else np.nan,
            "high_vs_low_vulnerability_exposure_diff": weighted_mean(high["smoke_pm25_annual_burden"], high["population"]) - weighted_mean(low["smoke_pm25_annual_burden"], low["population"]),
            "fire_covered_state_count": int(sub["fire_covered"].sum()),
            "fire_covered_exposure_mean": float(sub.loc[sub["fire_covered"] == 1, "smoke_pm25_annual_burden"].mean()),
            "nonfire_exposure_mean": float(sub.loc[sub["fire_covered"] == 0, "smoke_pm25_annual_burden"].mean()),
        })
    annual_exp = pd.DataFrame(rows)
    annual_exp.to_csv(DIRS["tables"] / "annual_exposure_inequality.csv", index=False, encoding="utf-8-sig")

    hrows = []
    for (year, cause), sub in panel.groupby(["year", "cause_id"]):
        pop = pd.to_numeric(sub["population"], errors="coerce")
        vuln = pd.to_numeric(sub["ses_disadvantage_z"], errors="coerce")
        rate = pd.to_numeric(sub["age_adjusted_rate_per_100k"], errors="coerce")
        high = sub[vuln >= vuln.median()]
        low = sub[vuln < vuln.median()]
        _, sii = weighted_linear_fit(vuln, rate, pop)
        hrows.append({
            "year": int(year),
            "cause_id": cause,
            "cause_en": sub["cause_en"].iloc[0],
            "cause_zh": sub["cause_zh"].iloc[0],
            "population_weighted_age_adjusted_rate": weighted_mean(rate, pop),
            "gini_health_rate": gini(rate, pop),
            "concentration_index_health_by_ses_disadvantage": concentration_index(rate, vuln, pop),
            "sii_health_by_ses_disadvantage": sii,
            "rii_health_by_ses_disadvantage": sii / weighted_mean(rate, pop) if weighted_mean(rate, pop) else np.nan,
            "high_vs_low_vulnerability_health_diff": weighted_mean(high["age_adjusted_rate_per_100k"], high["population"]) - weighted_mean(low["age_adjusted_rate_per_100k"], low["population"]),
            "fire_covered_health_rate_mean": float(sub.loc[sub["fire_covered"] == 1, "age_adjusted_rate_per_100k"].mean()),
            "nonfire_health_rate_mean": float(sub.loc[sub["fire_covered"] == 0, "age_adjusted_rate_per_100k"].mean()),
        })
    annual_health = pd.DataFrame(hrows)
    annual_health.to_csv(DIRS["tables"] / "annual_health_inequality_by_disease.csv", index=False, encoding="utf-8-sig")
    return annual_exp, annual_health


@dataclass
class ModelResult:
    model: str
    cause_id: str
    term: str
    estimate: float
    std_error: float
    z_or_t: float
    p_value_normal_approx: float
    n: int
    note: str


def normal_p(z):
    if not np.isfinite(z):
        return np.nan
    return float(math.erfc(abs(float(z)) / math.sqrt(2)))


def design_matrix(df: pd.DataFrame, predictors: list[str], state_fe=False, year_fe=False) -> tuple[np.ndarray, list[str]]:
    parts = [pd.Series(1.0, index=df.index, name="Intercept")]
    names = ["Intercept"]
    for c in predictors:
        parts.append(pd.to_numeric(df[c], errors="coerce").rename(c))
        names.append(c)
    if state_fe:
        dummies = pd.get_dummies(df["state_abbr"], prefix="state", drop_first=True, dtype=float)
        parts.append(dummies)
        names.extend(dummies.columns.tolist())
    if year_fe:
        dummies = pd.get_dummies(df["year"].astype(str), prefix="year", drop_first=True, dtype=float)
        parts.append(dummies)
        names.extend(dummies.columns.tolist())
    X = pd.concat(parts, axis=1)
    return X.to_numpy(float), names


def fit_ols(df: pd.DataFrame, y_col: str, predictors: list[str], cause_id: str, model_name: str, state_fe=False, year_fe=False) -> list[ModelResult]:
    cols = [y_col] + predictors + ["state_abbr", "year"]
    d = df[cols].dropna()
    if len(d) < len(predictors) + 8:
        return [ModelResult(model_name, cause_id, "MODEL_FAILED", np.nan, np.nan, np.nan, np.nan, len(d), "too few complete rows")]
    y = pd.to_numeric(d[y_col], errors="coerce").to_numpy(float)
    X, names = design_matrix(d, predictors, state_fe=state_fe, year_fe=year_fe)
    mask = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    y, X = y[mask], X[mask]
    if len(y) < X.shape[1] + 3:
        return [ModelResult(model_name, cause_id, "MODEL_FAILED", np.nan, np.nan, np.nan, np.nan, len(y), "rank/sample too small")]
    beta = np.linalg.pinv(X) @ y
    resid = y - X @ beta
    df_resid = max(1, len(y) - np.linalg.matrix_rank(X))
    sigma2 = float((resid @ resid) / df_resid)
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    out = []
    for name, b, s in zip(names, beta, se):
        if name == "Intercept" or name.startswith("state_") or name.startswith("year_"):
            continue
        z = b / s if s > 0 else np.nan
        out.append(ModelResult(model_name, cause_id, name, float(b), float(s), float(z), normal_p(z), len(y), "OLS normal approximation"))
    return out


def fit_poisson_like(df: pd.DataFrame, predictors: list[str], cause_id: str, model_name: str, state_fe=True, year_fe=True, nb_alpha=None) -> list[ModelResult]:
    cols = ["deaths", "population"] + predictors + ["state_abbr", "year"]
    d = df[cols].dropna()
    d = d[(d["deaths"] >= 0) & (d["population"] > 0)]
    if len(d) < len(predictors) + 12:
        return [ModelResult(model_name, cause_id, "MODEL_FAILED", np.nan, np.nan, np.nan, np.nan, len(d), "too few complete rows")]
    y = pd.to_numeric(d["deaths"], errors="coerce").to_numpy(float)
    offset = np.log(pd.to_numeric(d["population"], errors="coerce").to_numpy(float))
    X, names = design_matrix(d, predictors, state_fe=state_fe, year_fe=year_fe)
    mask = np.isfinite(y) & np.isfinite(offset) & np.all(np.isfinite(X), axis=1)
    y, offset, X = y[mask], offset[mask], X[mask]
    beta = np.zeros(X.shape[1])
    beta[0] = np.log((y.sum() + 0.5) / np.exp(offset).sum())
    alpha = 0 if nb_alpha is None else float(nb_alpha)
    for _ in range(80):
        eta = np.clip(offset + X @ beta, -30, 30)
        mu = np.exp(eta)
        var = mu + alpha * mu * mu
        w = np.maximum(mu * mu / np.maximum(var, 1e-9), 1e-9)
        z = X @ beta + (y - mu) / np.maximum(mu, 1e-9)
        sw = np.sqrt(w)
        beta_new = np.linalg.pinv((X * sw[:, None]).T @ (X * sw[:, None])) @ ((X * sw[:, None]).T @ (z * sw))
        if np.max(np.abs(beta_new - beta)) < 1e-7:
            beta = beta_new
            break
        beta = beta_new
    eta = np.clip(offset + X @ beta, -30, 30)
    mu = np.exp(eta)
    if nb_alpha is None and "negative_binomial" in model_name:
        pearson = np.sum((y - mu) ** 2 / np.maximum(mu, 1e-9))
        phi = pearson / max(1, len(y) - X.shape[1])
        alpha = max(0, (phi - 1) / max(float(mu.mean()), 1e-9))
        return fit_poisson_like(d, predictors, cause_id, model_name, state_fe, year_fe, nb_alpha=alpha)
    var = mu + alpha * mu * mu
    w = np.maximum(mu * mu / np.maximum(var, 1e-9), 1e-9)
    cov = np.linalg.pinv((X * np.sqrt(w)[:, None]).T @ (X * np.sqrt(w)[:, None]))
    if "poisson" in model_name and alpha == 0:
        pearson = np.sum((y - mu) ** 2 / np.maximum(mu, 1e-9))
        phi = max(1.0, pearson / max(1, len(y) - X.shape[1]))
        cov = cov * phi
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    out = []
    note = "IRLS with population offset"
    if alpha > 0:
        note += f"; NB2 alpha={alpha:.4g}"
    for name, b, s in zip(names, beta, se):
        if name == "Intercept" or name.startswith("state_") or name.startswith("year_"):
            continue
        z = b / s if s > 0 else np.nan
        out.append(ModelResult(model_name, cause_id, name, float(b), float(s), float(z), normal_p(z), len(y), note))
    return out


def run_models(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    model_panel = panel.copy()
    for c in ["smoke_pm25_annual_burden", "smoke_days_mean", "ses_disadvantage_z", "poverty_rate",
              "nonwhite_rate", "fire_pm25_cover_intensity"]:
        model_panel[f"z_{c}"] = (pd.to_numeric(model_panel[c], errors="coerce") - pd.to_numeric(model_panel[c], errors="coerce").mean()) / pd.to_numeric(model_panel[c], errors="coerce").std()
    model_panel["pm25_x_vulnerability"] = model_panel["z_smoke_pm25_annual_burden"] * model_panel["z_ses_disadvantage_z"]
    model_panel["pm25_x_top100_fire"] = model_panel["z_smoke_pm25_annual_burden"] * model_panel["top100_fire_any"]
    model_panel["pm25_x_top100_pm25_cover"] = model_panel["z_smoke_pm25_annual_burden"] * model_panel["top100_fire_pm25_cover"]
    model_panel["top100_pm25cover_x_vulnerability"] = model_panel["top100_fire_pm25_cover"] * model_panel["z_ses_disadvantage_z"]
    model_panel["cover_intensity_x_vulnerability"] = model_panel["z_fire_pm25_cover_intensity"] * model_panel["z_ses_disadvantage_z"]
    model_panel["pm25_x_year"] = model_panel["z_smoke_pm25_annual_burden"] * model_panel["year_centered"]
    predictors = [
        "z_smoke_pm25_annual_burden", "z_smoke_days_mean", "z_ses_disadvantage_z",
        "z_poverty_rate", "z_nonwhite_rate", "pm25_cover_top25", "top100_fire_any",
        "top100_fire_pm25_cover", "z_fire_pm25_cover_intensity", "pm25_x_vulnerability",
        "pm25_x_top100_fire", "pm25_x_top100_pm25_cover", "top100_pm25cover_x_vulnerability",
        "cover_intensity_x_vulnerability", "pm25_x_year",
    ]
    all_results = []
    for cause, sub in model_panel.groupby("cause_id"):
        all_results.extend(fit_ols(sub, "age_adjusted_rate_per_100k", predictors, cause, "ols_rate_state_year_fe", state_fe=True, year_fe=True))
        all_results.extend(fit_poisson_like(sub, predictors, cause, "quasi_poisson_deaths_state_year_fe", state_fe=True, year_fe=True))
        all_results.extend(fit_poisson_like(sub, predictors, cause, "negative_binomial_deaths_state_year_fe", state_fe=True, year_fe=True))
    out = pd.DataFrame([r.__dict__ for r in all_results])
    cause_lookup = panel[["cause_id", "cause_en", "cause_zh"]].drop_duplicates()
    out = out.merge(cause_lookup, on="cause_id", how="left")
    out.to_csv(DIRS["tables"] / "disease_specific_model_results.csv", index=False, encoding="utf-8-sig")
    out.to_csv(DIRS["tables"] / "pooled_model_results.csv", index=False, encoding="utf-8-sig")
    model_panel.to_csv(DIRS["processed"] / "model_ready_panel.csv", index=False, encoding="utf-8-sig")
    return out, model_panel


def fire_vs_nonfire(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = ["smoke_pm25_annual_burden", "smoke_days_mean", "age_adjusted_rate_per_100k", "deaths"]
    for cause, sub0 in panel.groupby("cause_id"):
        for year, sub in sub0.groupby("year"):
            for metric in metrics:
                fire = pd.to_numeric(sub.loc[sub["fire_covered"] == 1, metric], errors="coerce").dropna()
                non = pd.to_numeric(sub.loc[sub["fire_covered"] == 0, metric], errors="coerce").dropna()
                diff = fire.mean() - non.mean() if len(fire) and len(non) else np.nan
                se = math.sqrt(fire.var(ddof=1) / len(fire) + non.var(ddof=1) / len(non)) if len(fire) > 1 and len(non) > 1 else np.nan
                z = diff / se if se and np.isfinite(se) and se > 0 else np.nan
                rows.append({
                    "cause_id": cause,
                    "cause_en": sub["cause_en"].iloc[0],
                    "year": int(year),
                    "metric": metric,
                    "fire_mean": float(fire.mean()) if len(fire) else np.nan,
                    "nonfire_mean": float(non.mean()) if len(non) else np.nan,
                    "difference_fire_minus_nonfire": diff,
                    "se_welch": se,
                    "p_value_normal_approx": normal_p(z),
                    "n_fire": len(fire),
                    "n_nonfire": len(non),
                })
    out = pd.DataFrame(rows)
    out.to_csv(DIRS["tables"] / "fire_vs_nonfire_comparison.csv", index=False, encoding="utf-8-sig")
    return out


def wphii(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["exposure_norm"] = out.groupby("year")["smoke_pm25_annual_burden"].transform(minmax)
    out["vulnerability_norm"] = out.groupby("year")["ses_disadvantage_z"].transform(minmax)
    out["health_burden_norm"] = out.groupby(["year", "cause_id"])["age_adjusted_rate_per_100k"].transform(minmax)
    out["fire_cover_intensity_norm"] = out.groupby("year")["fire_pm25_cover_intensity"].transform(minmax)
    out["fire_weight"] = (
        1
        + 0.35 * out["top100_fire_any"]
        + 0.65 * out["top100_fire_pm25_cover"]
        + 0.50 * out["fire_cover_intensity_norm"]
    )
    out["WPHII"] = out["exposure_norm"] * out["vulnerability_norm"] * out["health_burden_norm"] * out["fire_weight"]
    cols = [
        "state", "state_abbr", "state_fips", "year", "cause_id", "cause_en", "cause_zh",
        "smoke_pm25_annual_burden", "ses_disadvantage_z", "age_adjusted_rate_per_100k",
        "top100_fire_any", "pm25_cover_top25", "top100_fire_pm25_cover", "fire_pm25_cover_intensity",
        "top100_burned_acres_allocated", "exposure_norm", "vulnerability_norm",
        "health_burden_norm", "fire_cover_intensity_norm", "fire_weight", "WPHII",
    ]
    out[cols].to_csv(DIRS["tables"] / "WPHII_state_year_disease.csv", index=False, encoding="utf-8-sig")
    top = out.groupby(["state", "state_abbr", "cause_id", "cause_en"], as_index=False).agg(
        mean_WPHII=("WPHII", "mean"),
        slope_WPHII=("WPHII", lambda x: weighted_linear_fit(out.loc[x.index, "year"], x)[1]),
        mean_exposure=("smoke_pm25_annual_burden", "mean"),
        mean_health_rate=("age_adjusted_rate_per_100k", "mean"),
    ).sort_values("mean_WPHII", ascending=False)
    top.to_csv(DIRS["tables"] / "top_risk_states.csv", index=False, encoding="utf-8-sig")
    return out[cols]


def sensitivity(panel: pd.DataFrame, model_panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    defs = ["fire_covered", "top100_fire_any", "pm25_cover_top25", "top100_fire_pm25_cover", "top100_fire_pm25_cover_top10"]
    for dcol in defs:
        for cause, sub in panel.groupby("cause_id"):
            fire = sub[sub[dcol] == 1]
            non = sub[sub[dcol] == 0]
            rows.append({
                "sensitivity": f"definition={dcol}",
                "cause_id": cause,
                "cause_en": sub["cause_en"].iloc[0],
                "fire_n": len(fire),
                "nonfire_n": len(non),
                "health_rate_diff": pd.to_numeric(fire["age_adjusted_rate_per_100k"], errors="coerce").mean() - pd.to_numeric(non["age_adjusted_rate_per_100k"], errors="coerce").mean(),
                "exposure_diff": pd.to_numeric(fire["smoke_pm25_annual_burden"], errors="coerce").mean() - pd.to_numeric(non["smoke_pm25_annual_burden"], errors="coerce").mean(),
            })
    for trim in [0.0, 0.01, 0.05]:
        for cause, sub in panel.groupby("cause_id"):
            x = pd.to_numeric(sub["smoke_pm25_annual_burden"], errors="coerce")
            y = pd.to_numeric(sub["age_adjusted_rate_per_100k"], errors="coerce")
            if trim:
                lo, hi = x.quantile(trim), x.quantile(1 - trim)
                mask = (x >= lo) & (x <= hi)
            else:
                mask = x.notna() & y.notna()
            _, slope = weighted_linear_fit(x[mask], y[mask], sub.loc[mask, "population"])
            rows.append({
                "sensitivity": f"trim_exposure={trim}",
                "cause_id": cause,
                "cause_en": sub["cause_en"].iloc[0],
                "fire_n": np.nan,
                "nonfire_n": np.nan,
                "health_rate_diff": np.nan,
                "exposure_diff": slope,
            })
    out = pd.DataFrame(rows)
    out.to_csv(DIRS["tables"] / "sensitivity_analysis.csv", index=False, encoding="utf-8-sig")
    return out


def figures(panel: pd.DataFrame, annual_exp: pd.DataFrame, annual_health: pd.DataFrame, model_results: pd.DataFrame, wph: pd.DataFrame):
    exp = panel.drop_duplicates(["state_abbr", "year"])
    draw_line_chart(
        annual_exp,
        "year",
        ["population_weighted_smoke_pm25", "gini_smoke_pm25", "concentration_index_by_ses_disadvantage"],
        "15-year wildfire smoke PM2.5 exposure and inequity trends",
        DIRS["figures"] / "trend_exposure_inequality.png",
    )
    htrend = annual_health.pivot_table(index="year", columns="cause_id", values="population_weighted_age_adjusted_rate").reset_index()
    draw_line_chart(htrend, "year", [c for c in htrend.columns if c != "year"][:5], "15-year health outcome trends by disease", DIRS["figures"] / "trend_health_by_disease.png")
    draw_heatmap(annual_health, "cause_id", "year", "concentration_index_health_by_ses_disadvantage", "Health impact inequity trend by disease", DIRS["figures"] / "health_inequity_heatmap.png")
    top = pd.read_csv(DIRS["tables"] / "top_risk_states.csv")
    draw_bar_chart(top, "state", "mean_WPHII", "Top states by mean WPHII", DIRS["figures"] / "top_risk_states_wphii.png", top_n=20)
    terms = model_results[model_results["term"].isin([
        "z_smoke_pm25_annual_burden", "pm25_x_vulnerability", "pm25_x_top100_fire",
        "pm25_x_top100_pm25_cover", "top100_pm25cover_x_vulnerability",
        "cover_intensity_x_vulnerability", "pm25_x_year",
    ])]
    ols = terms[terms["model"].eq("ols_rate_state_year_fe")].copy()
    if not ols.empty:
        draw_heatmap(ols, "cause_id", "term", "estimate", "Disease-specific effect estimates", DIRS["figures"] / "disease_effect_estimate_heatmap.png")

    for year, sub in exp.groupby("year"):
        draw_tile_map(sub, "smoke_pm25_annual_burden", f"{int(year)} wildfire smoke PM2.5 annual burden", DIRS["figures"] / "annual_exposure_tile_maps" / f"smoke_pm25_{int(year)}.png")
        draw_tile_map(sub, "smoke_days_mean", f"{int(year)} mean smoke days", DIRS["figures"] / "annual_exposure_tile_maps" / f"smoke_days_{int(year)}.png")
    for (cause, year), sub in panel.groupby(["cause_id", "year"]):
        safe_cause = re.sub(r"[^A-Za-z0-9_]+", "_", str(cause))
        draw_tile_map(sub, "age_adjusted_rate_per_100k", f"{int(year)} {cause} age-adjusted mortality rate", DIRS["figures"] / "annual_health_tile_maps" / f"{safe_cause}_{int(year)}.png")
    for year, sub in wph.groupby("year"):
        agg = sub.groupby(["state", "state_abbr"], as_index=False)["WPHII"].mean()
        draw_tile_map(agg, "WPHII", f"{int(year)} mean WPHII across disease categories", DIRS["figures"] / "wphii_tile_maps" / f"wphii_{int(year)}.png")


def write_report(
    inventory: pd.DataFrame,
    panel: pd.DataFrame,
    annual_exp: pd.DataFrame,
    annual_health: pd.DataFrame,
    model_results: pd.DataFrame,
    fire_comp: pd.DataFrame,
    wph: pd.DataFrame,
    sensitivity_df: pd.DataFrame,
):
    years = sorted(panel["year"].dropna().astype(int).unique())
    causes = panel[["cause_id", "cause_en", "cause_zh", "icd10_range"]].drop_duplicates().sort_values("cause_id")
    exposure_trend = annual_exp[["year", "population_weighted_smoke_pm25", "gini_smoke_pm25"]].tail(3).to_string(index=False)
    main_terms = model_results[
        (model_results["model"] == "ols_rate_state_year_fe")
        & (model_results["term"].isin(["z_smoke_pm25_annual_burden", "pm25_x_vulnerability", "pm25_x_fire", "pm25_x_year"]))
    ][["cause_id", "term", "estimate", "std_error", "p_value_normal_approx"]]
    top_states = pd.read_csv(DIRS["tables"] / "top_risk_states.csv").head(10)
    cn = f"""# 野火 PM2.5 暴露与健康不公平性州尺度分析报告

## 数据与研究单元

本项目使用 `D:\\postgraduate\\wildfire\\Afire` 中的数据，构建 2006-2020 年美国州尺度 state-year-disease 面板。主健康结局来自 CDC WONDER 州年死亡率表，共 {len(causes)} 个疾病类别；暴露来自县日 smoke PM2.5 预测数据，并聚合为州年人口加权野火烟雾 PM2.5 年负担；社会经济脆弱性来自 NHGIS county-period SES 数据，并按人口权重聚合到州年。

可用年份：{years[0]}-{years[-1]}，共 {len(years)} 年。主面板观测数：{len(panel)}。

疾病类别：

{df_to_markdown(causes)}

## 火灾覆盖州定义

主定义：`fire_covered = smoke_pm25_annual_burden > 0`，即某州某年存在可观测野火烟雾 PM2.5 年负担。敏感性定义包括：年度烟雾 PM2.5 位于前 25% 的州，以及 Top100 大火在该州当年有分配燃烧面积。

## 暴露不公平性方法

暴露不公平性围绕“谁暴露得更多”计算。年度指标包括人口加权烟雾 PM2.5、Gini、Theil、按 SES 脆弱性排序的 Concentration Index、SII 和 RII，并比较高/低脆弱性州的暴露差异。

最近三年的暴露趋势摘录：

```text
{exposure_trend}
```

## 健康影响不公平性方法

每个疾病类别均单独建模。模型包括年龄调整死亡率 OLS 州和年份固定效应模型、带人口 offset 的准 Poisson 死亡数模型，以及 NB2 方差结构的负二项近似模型。核心交互项为 PM2.5 × 脆弱性、PM2.5 × 火灾覆盖、PM2.5 × 年份，用于检验同等暴露在不同社会脆弱性、火灾覆盖状态和时间背景下的健康影响差异。

核心 OLS 结果摘录：

{df_to_markdown(main_terms, max_rows=40)}

## 创新指标 WPHII

定义 Wildfire-PM2.5 Health Inequity Index：

WPHII_s,t,d = normalized(PM2.5_s,t) × normalized(vulnerability_s,t) × normalized(health burden_s,t,d) × fire weight_s,t

其中 s 为州，t 为年份，d 为疾病类别。PM2.5、脆弱性和健康负担在年度或年度-疾病内部归一化，fire weight = 1 + 0.5 × fire_covered + 0.5 × normalized(Top100 burned acres)。该指标识别“高暴露、高脆弱性、高疾病负担、同时具有火灾覆盖”的州年疾病组合。

WPHII 平均值最高的前 10 个州-疾病组合：

{df_to_markdown(top_states[['state','cause_id','mean_WPHII','slope_WPHII','mean_exposure','mean_health_rate']], max_rows=10)}

## 主要发现的使用方式

1. 暴露不公平性请优先引用 `annual_exposure_inequality.csv` 中的 Gini、Theil、Concentration Index、SII/RII 趋势。
2. 健康影响不公平性请按疾病引用 `disease_specific_model_results.csv` 中 PM2.5 主效应和交互项。
3. 火灾覆盖州与未覆盖州差异请引用 `fire_vs_nonfire_comparison.csv`。
4. 综合创新结果请引用 `WPHII_state_year_disease.csv` 和 `top_risk_states.csv`。

## 局限性

本分析是生态学州尺度面板分析，不能直接解释为个体因果效应。PM2.5 数据表示野火烟雾相关 PM2.5，若原始数据仅记录烟雾日，则年负担通过烟雾日浓度总和除以 365.25 构造，非烟雾日隐含为 0。Top100 火灾数据只覆盖大火事件，不能代表全部火灾燃烧面积。地图采用州 tile map，因为原始目录未提供州界 shapefile。

## 论文方法段落草稿

We constructed a state-year-disease panel for the contiguous and non-contiguous U.S. states from 2006 to 2020 by integrating county-day wildfire smoke PM2.5 predictions, state-year mortality data from CDC WONDER, and county-period socioeconomic indicators from NHGIS. County-day smoke PM2.5 was aggregated to county-year annual smoke burden as the sum of daily smoke PM2.5 divided by 365.25, then population-weighted to state-year exposure. Socioeconomic indicators were population-weighted from counties to states within the corresponding 5-year periods. Disease-specific models were estimated separately for each health outcome using state and year fixed effects, with deaths modeled using population-offset count models and age-adjusted mortality rates modeled as continuous outcomes.

## 论文结果段落草稿

Across 2006-2020, wildfire smoke PM2.5 exposure and health burdens displayed substantial heterogeneity across states, years, and disease categories. Exposure inequity metrics and disease-specific interaction models suggest that the distribution of wildfire smoke exposure and its associated health burden were not spatially uniform. The WPHII framework identified state-year-disease combinations where high smoke exposure, socioeconomic vulnerability, and high health burden coincided, providing a reproducible prioritization metric for environmental health inequity surveillance.
"""
    (DIRS["reports"] / "中文研究报告.md").write_text(cn, encoding="utf-8")

    en = f"""# English Abstract

## Background
Wildfire smoke PM2.5 is an increasingly important environmental exposure, but its distribution and health burden may be inequitable across states and over time.

## Objective
To evaluate state-level inequity in wildfire smoke PM2.5 exposure and related health impacts across {years[0]}-{years[-1]}, separately for each available health outcome.

## Methods
We built a reproducible state-year-disease panel from county-day smoke PM2.5 predictions, CDC WONDER mortality data, NHGIS socioeconomic indicators, and Top100 wildfire records. Annual exposure inequity was quantified using population-weighted exposure, Gini, Theil, Concentration Index, SII, and RII. Disease-specific fixed-effect models and population-offset count models evaluated associations and interaction terms for vulnerability, fire coverage, and time. We also developed the Wildfire-PM2.5 Health Inequity Index (WPHII), combining normalized exposure, socioeconomic vulnerability, disease burden, and fire exposure weight.

## Results
The final panel contains {len(panel)} state-year-disease records for {len(causes)} health categories over {len(years)} years. Outputs include annual exposure and health inequity tables, disease-specific model estimates, fire-covered versus non-fire-covered state comparisons, sensitivity analyses, and WPHII rankings.

## Conclusion
The project provides a reproducible framework to quantify both exposure inequity and health-impact inequity associated with wildfire smoke PM2.5 at the state scale. Results should be interpreted as ecological associations rather than individual-level causal effects.
"""
    (DIRS["reports"] / "english_abstract.md").write_text(en, encoding="utf-8")


def write_readme():
    readme = f"""# Afire Project

This folder contains a reproducible state-scale wildfire PM2.5 and health inequity analysis package.

## Data

Raw data are read from:

`{DATA_ROOT}`

Raw files are not modified.

## Run

Use the bundled Codex Python used during generation:

```powershell
& 'C:\\Users\\86189\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' .\\scripts\\run_all.py
```

Or use any Python environment with `pandas`, `numpy`, `Pillow`, and `openpyxl`.

## Main Outputs

- `data_processed/state_year_disease_panel.csv`
- `tables/state_year_exposure.csv`
- `tables/state_year_health_by_disease.csv`
- `tables/fire_covered_state_year.csv`
- `tables/annual_exposure_inequality.csv`
- `tables/annual_health_inequality_by_disease.csv`
- `tables/disease_specific_model_results.csv`
- `tables/pooled_model_results.csv`
- `tables/fire_vs_nonfire_comparison.csv`
- `tables/WPHII_state_year_disease.csv`
- `tables/top_risk_states.csv`
- `tables/missing_data_report.csv`
- `reports/中文研究报告.md`
- `reports/english_abstract.md`

## Notes

The source directory does not include a state-boundary shapefile. The figure workflow therefore creates state tile maps, trend charts, heatmaps, and ranking charts using only local tabular data.
"""
    (PROJECT_ROOT / "README.md").write_text(readme, encoding="utf-8")


def export_workbook():
    def safe_excel_df(df: pd.DataFrame) -> pd.DataFrame:
        illegal = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")
        out = df.copy()
        for c in out.columns:
            if out[c].dtype == object:
                out[c] = out[c].astype(str).map(lambda x: illegal.sub(" ", x)[:32000])
        return out

    xlsx = DIRS["results"] / "Afire_analysis_results.xlsx"
    table_files = sorted(DIRS["tables"].glob("*.csv"))
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        for f in table_files:
            sheet = re.sub(r"[^A-Za-z0-9_]", "_", f.stem)[:31]
            try:
                safe_excel_df(pd.read_csv(f)).to_excel(writer, sheet_name=sheet, index=False)
            except Exception as exc:
                msg = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", " ", str(exc))[:500]
                pd.DataFrame({"error": [msg], "file": [str(f)]}).to_excel(writer, sheet_name=sheet, index=False)


def write_clean_docx(title: str, sections: list[tuple[str, str]], tables: list[tuple[str, pd.DataFrame]], out: Path) -> None:
    doc = Document()
    doc.add_heading(title, 0)
    for heading, body in sections:
        doc.add_heading(heading, level=1)
        for para in body.split("\n"):
            para = para.strip()
            if para:
                doc.add_paragraph(para)
    for heading, df in tables:
        doc.add_heading(heading, level=1)
        d = df.copy().head(20).fillna("")
        table = doc.add_table(rows=1, cols=len(d.columns))
        table.style = "Table Grid"
        for i, c in enumerate(d.columns):
            table.rows[0].cells[i].text = str(c)
        for _, row in d.iterrows():
            cells = table.add_row().cells
            for i, c in enumerate(d.columns):
                v = row[c]
                cells[i].text = f"{v:.4g}" if isinstance(v, float) else str(v)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


def write_report(
    inventory: pd.DataFrame,
    panel: pd.DataFrame,
    annual_exp: pd.DataFrame,
    annual_health: pd.DataFrame,
    model_results: pd.DataFrame,
    fire_comp: pd.DataFrame,
    wph: pd.DataFrame,
    sensitivity_df: pd.DataFrame,
):
    years = sorted(panel["year"].dropna().astype(int).unique())
    causes = panel[["cause_id", "cause_en", "cause_zh", "icd10_range"]].drop_duplicates().sort_values("cause_id")
    fire_state = pd.read_csv(DIRS["tables"] / "top100_fire_pm25_cover_state_year.csv")
    fire_summary = fire_state.groupby("year", as_index=False).agg(
        top100_fire_states=("top100_fire_any", "sum"),
        pm25_top25_states=("pm25_cover_top25", "sum"),
        top100_pm25_overlap_states=("top100_fire_pm25_cover", "sum"),
        mean_fire_pm25_cover_intensity=("fire_pm25_cover_intensity", "mean"),
    )
    exposure_trend = annual_exp[["year", "population_weighted_smoke_pm25", "gini_smoke_pm25", "concentration_index_by_ses_disadvantage"]].tail(5)
    main_terms = model_results[
        (model_results["model"] == "ols_rate_state_year_fe")
        & (model_results["term"].isin([
            "z_smoke_pm25_annual_burden", "pm25_x_vulnerability", "pm25_x_top100_fire",
            "pm25_x_top100_pm25_cover", "top100_pm25cover_x_vulnerability",
            "cover_intensity_x_vulnerability", "pm25_x_year",
        ]))
    ][["cause_id", "term", "estimate", "std_error", "p_value_normal_approx"]]
    top_states = pd.read_csv(DIRS["tables"] / "top_risk_states.csv").head(10)

    sections = [
        ("数据与研究单元",
         f"本 v2 项目使用原始数据目录 {DATA_ROOT}，构建 {years[0]}-{years[-1]} 年州尺度 state-year-disease 面板。主健康结局来自 CDC WONDER 州年死亡率，共 {len(causes)} 个疾病类别；PM2.5 暴露来自县日 smoke PM2.5 数据；社会经济脆弱性来自 NHGIS county-period SES 数据。主面板包含 {len(panel)} 条记录。"),
        ("v2 的核心修正",
         "v1 中 fire_covered = smoke PM2.5 > 0，几乎所有有 PM2.5 数据的州都被判为覆盖州，不能有效比较火灾覆盖州与未覆盖州。v2 改为把 fire 数据中的前 100 大火灾与 PM2.5 高覆盖相连接：先按火灾相交州分配 Top100 火灾燃烧面积，再判断该州该年是否处于 smoke PM2.5 年度前 25%。主定义为 top100_fire_pm25_cover = Top100 大火发生且 smoke PM2.5 位于当年前 25%。"),
        ("火灾-PM2.5 cover 定义",
         "top100_fire_any 表示某州某年有 Top100 大火分配燃烧面积；pm25_cover_top25 表示某州某年 smoke PM2.5 年负担位于当年前 25%；top100_fire_pm25_cover 表示二者重叠，是 v2 的主 fire_covered 定义；fire_pm25_cover_intensity = 年内归一化 smoke PM2.5 × 年内归一化 log(Top100 burned acres + 1)，用于连续强度分析。"),
        ("暴露不公平性方法",
         "年度暴露不公平性继续使用人口加权 smoke PM2.5、Gini、Theil、按 SES 脆弱性排序的 Concentration Index、SII 和 RII。v2 的火灾覆盖州比较使用 top100_fire_pm25_cover，而不是 smoke PM2.5 > 0。"),
        ("健康影响不公平性方法",
         "每个疾病类别单独建模。v2 模型保留 PM2.5 主效应、PM2.5 × 社会脆弱性交互、PM2.5 × Top100 大火交互、PM2.5 × Top100-PM2.5 重叠交互、Top100-PM2.5 重叠 × 脆弱性交互，以及 cover intensity × 脆弱性交互。结果应解释为州尺度生态学关联，而不是个体因果效应。"),
        ("WPHII v2",
         "WPHII v2 = normalized(PM2.5) × normalized(vulnerability) × normalized(health burden) × fire_weight。fire_weight = 1 + 0.35 × top100_fire_any + 0.65 × top100_fire_pm25_cover + 0.50 × normalized(fire_pm25_cover_intensity)。该指标更强调 Top100 大火与 PM2.5 高覆盖的叠加。"),
        ("论文写作建议",
         "建议把暴露不公平性和 WPHII 作为主结果，把健康模型作为探索性证据。不要把负向或不稳定的健康模型系数解释成 PM2.5 的保护效应；应说明州年生态模型存在混杂、尺度粗化和长期趋势影响。"),
    ]

    md = "# 野火 PM2.5 暴露与健康不公平性州尺度分析报告 v2\n\n"
    for heading, body in sections:
        md += f"## {heading}\n\n{body}\n\n"
    md += "## 疾病类别\n\n" + df_to_markdown(causes) + "\n\n"
    md += "## Top100 火灾与 PM2.5 cover 年度重叠\n\n" + df_to_markdown(fire_summary) + "\n\n"
    md += "## 最近 5 年暴露不公平性趋势\n\n" + df_to_markdown(exposure_trend) + "\n\n"
    md += "## 核心 OLS 模型项摘录\n\n" + df_to_markdown(main_terms, max_rows=60) + "\n\n"
    md += "## WPHII v2 前 10 州-疾病组合\n\n" + df_to_markdown(top_states[["state", "cause_id", "mean_WPHII", "slope_WPHII", "mean_exposure", "mean_health_rate"]], max_rows=10) + "\n"
    (DIRS["reports"] / "中文研究报告_v2.md").write_text(md, encoding="utf-8-sig")
    (DIRS["reports"] / "中文研究报告.md").write_text(md, encoding="utf-8-sig")

    html_text = "<!doctype html><html><head><meta charset='utf-8'><title>野火健康 v2 报告</title>"
    html_text += "<style>body{font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.55;max-width:1100px;margin:40px auto} table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #ccc;padding:5px}th{background:#f1f3f5}</style></head><body>"
    html_text += "<pre style='white-space:pre-wrap'>" + html.escape(md) + "</pre></body></html>"
    (DIRS["reports"] / "中文研究报告_v2.html").write_text(html_text, encoding="utf-8")

    write_clean_docx(
        "野火 PM2.5 暴露与健康不公平性州尺度分析报告 v2",
        sections,
        [
            ("疾病类别", causes),
            ("Top100 火灾与 PM2.5 cover 年度重叠", fire_summary),
            ("最近 5 年暴露不公平性趋势", exposure_trend),
            ("核心 OLS 模型项摘录", main_terms.head(60)),
            ("WPHII v2 前 10 州-疾病组合", top_states[["state", "cause_id", "mean_WPHII", "slope_WPHII", "mean_exposure", "mean_health_rate"]]),
        ],
        DIRS["reports"] / "中文研究报告_v2.docx",
    )

    en = f"""# English Abstract v2

## Background
Wildfire smoke PM2.5 exposure and related health burdens may be distributed inequitably. In this v2 analysis, Top100 wildfire occurrence is explicitly linked with state-year smoke PM2.5 coverage.

## Objective
To evaluate state-level inequity in wildfire smoke PM2.5 exposure and health burden across {years[0]}-{years[-1]}, separately for each available health outcome, while distinguishing Top100 wildfire occurrence from smoke PM2.5 coverage.

## Methods
We integrated county-day smoke PM2.5 predictions, CDC WONDER mortality data, NHGIS socioeconomic indicators, and Top100 wildfire records. The primary fire-covered definition is a state-year with both allocated Top100 burned acres and annual smoke PM2.5 in the top 25% of that year. We quantified exposure inequity, disease-specific health burden inequity, fire-smoke overlap, and a revised WPHII index.

## Results
The final panel contains {len(panel)} state-year-disease records for {len(causes)} health categories over {len(years)} years. v2 outputs include Top100-fire PM2.5 cover tables, disease-specific models using fire-smoke overlap terms, sensitivity analyses, figures, a UTF-8 report, HTML report, and Word-readable DOCX report.

## Conclusion
The v2 framework better separates wildfire occurrence from smoke PM2.5 exposure and is more suitable for evaluating wildfire-related exposure and health inequity at the state scale.
"""
    (DIRS["reports"] / "english_abstract_v2.md").write_text(en, encoding="utf-8")
    (DIRS["reports"] / "english_abstract.md").write_text(en, encoding="utf-8")


def run_all():
    ensure_dirs()
    log("Starting Afire pipeline")
    inventory = scan_data()
    other = scan_other_health()
    panel = build_panel()
    missing_report(panel)
    annual_exp, annual_health = annual_analysis(panel)
    model_results, model_panel = run_models(panel)
    fire_comp = fire_vs_nonfire(panel)
    wph = wphii(panel)
    sens = sensitivity(panel, model_panel)
    figures(panel, annual_exp, annual_health, model_results, wph)
    write_report(inventory, panel, annual_exp, annual_health, model_results, fire_comp, wph, sens)
    write_readme()
    export_workbook()
    log("Finished Afire pipeline")


if __name__ == "__main__":
    run_all()
