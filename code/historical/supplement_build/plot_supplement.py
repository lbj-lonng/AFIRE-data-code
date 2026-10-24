"""Rebuild seven supplementary figures from frozen author-provided values.

This is a descriptive rendering workflow. It never fits a model, reallocates
counts, computes inferential intervals or changes multiplicity correction.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / "AFIRE_2009_2020_five_outcomes_20260915_194616"
FROZEN = BASE / "submission/source_data/full_results"
FIG = ROOT / "submission/figures"
DATA = ROOT / "submission/source_data/figures"
QA = ROOT / "audit/figures"
HELPERS = ROOT / "scripts/figure_qa_helpers"
for directory in (FIG, DATA, QA, QA / "tmp", QA / "mpl", HELPERS):
    directory.mkdir(parents=True, exist_ok=True)
for key in ("TEMP", "TMP", "TMPDIR"):
    os.environ[key] = str(QA / "tmp")
os.environ["MPLCONFIGDIR"] = str(QA / "mpl")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.extend([
    str(HELPERS),
    "C:/Users/86189/Documents/Codex/2026-09-10/ban/work/pydeps",
    "D:/postgraduate/wildfire/9.10/AFIRE_threepart_mainfig_redesign_20260912_173900/_work/deps",
])
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from audit_panel_alignment import require_matplotlib_panel_alignment

IDS = ["copd", "chronic_lower_respiratory", "respiratory_system",
       "circulatory_system", "ischemic_heart_disease"]
LABELS = ["COPD", "CLRD", "RESP", "CIRC", "IHD"]
SIX = ["AZ", "CA", "CO", "ID", "OR", "WA"]
BLUE, ORANGE, BLACK = "#226A8F", "#BB652F", "#242A2E"
matplotlib.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7.5, "legend.fontsize": 7,
    "axes.linewidth": 0.8, "lines.linewidth": 1.1,
    "svg.fonttype": "none", "pdf.fonttype": 42,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "savefig.facecolor": "white",
})

SOURCES = {
    1: (6, "county_aggregated_state_year", 72),
    2: (7, "county_map_values", 256),
    3: (5, "nested_outcome_check", 3),
    4: (1, "conditional", 25),
    5: (2, "common_sample", 40),
    6: (3, "targeted_omissions", 25),
    7: (4, "LST_pairs", 40),
}
MAP = []
CHECKS = []
MANIFEST = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_source(number):
    old, source, expected_rows = SOURCES[number]
    path = FROZEN / (source + ".csv")
    digest = sha(path)
    destination = DATA / f"Supplementary_Figure_{number}.csv"
    # A byte-identical local source copy prevents float re-serialization drift.
    shutil.copyfile(path, destination)
    d = pd.read_csv(destination, dtype={"county_fips": str, "state_fips": str},
                    float_precision="round_trip")
    assert len(d) == expected_rows
    if "year" in d:
        assert d.year.between(2009, 2020).all()
    if "outcome_id" in d:
        assert set(d.outcome_id) == set(IDS)
        assert d.year_min.eq(2009).all() and d.year_max.le(2020).all()
        key = ["outcome_id", "analysis_block", "model_id", "contrast_id"]
        assert not d.duplicated(key).any()
        assert d.n_imputations.eq(30).all()
        assert np.isfinite(d[["percent_estimate", "percent_CI_lower", "percent_CI_upper"]]).all().all()
    assert sha(destination) == digest
    MAP.append({"new_figure": number, "old_figure": f"S{old}",
                "source_file": str(path), "source_sha256": digest,
                "source_rows": len(d), "displayed_rows": len(d),
                "excluded_rows": 0, "source_data": str(destination.relative_to(ROOT)),
                "transformation": "None for estimates/intervals; descriptive means/box summaries only for Fig. 2",
                "plotting_script": "scripts/plot_supplement.py"})
    MANIFEST.append({"path": str(path), "sha256_before": digest})
    return d


def axes(fig, rect, gid):
    width, height = fig.get_size_inches() * 25.4
    ax = fig.add_axes([rect[0] / width, rect[1] / height,
                       rect[2] / width, rect[3] / height])
    ax.set_gid(gid)
    return ax


def title(ax, letter, label):
    ax.annotate(letter, (0, 1), xycoords="axes fraction", xytext=(-11, 7),
                textcoords="offset points", va="bottom", fontweight="bold", fontsize=8)
    ax.annotate(label, (0, 1), xycoords="axes fraction", xytext=(0, 7),
                textcoords="offset points", va="bottom", fontsize=8)


def run_audit(tool, args, log):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / tool), *args],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env)
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    print(tool, result.returncode, flush=True)
    if result.returncode != 0:
        raise RuntimeError(f"QA did not pass: {tool}; see {log}")
    return result


def save(fig, number, panel_axes, rows=None, cols=None):
    name = f"Supplementary_Figure_{number}"
    fig.canvas.draw()
    alignment = require_matplotlib_panel_alignment(
        fig, axes=panel_axes, row_groups=rows, column_groups=cols,
        json_out=QA / (name + ".alignment.json"),
        overlay_svg=QA / (name + ".alignment.svg"),
        tolerance_pt=1.5, gutter_tolerance_pt=1.5,
        require_panel_labels=True, strict=True,
    )
    (QA / (name + ".geometry.json")).write_text(json.dumps({
        "dimensions_mm": list(fig.get_size_inches() * 25.4),
        "intended_embedding_width_mm": 170,
        "panels": [{"id": a.get_gid(), "position": list(a.get_position().bounds),
                    "xlim": list(a.get_xlim()), "ylim": list(a.get_ylim())}
                   for a in panel_axes],
    }, indent=2), encoding="utf-8")
    for extension in ("pdf", "svg"):
        fig.savefig(FIG / (name + "." + extension))
    fig.savefig(FIG / (name + ".png"), dpi=600)
    fig.savefig(QA / (name + ".final_size.png"), dpi=300)
    # Render the exported PDF at the intended Word width: all glyphs scale too.
    import fitz
    with fitz.open(FIG / (name + ".pdf")) as document:
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(300 / 72 * 170 / 183,
                                                         300 / 72 * 170 / 183))
        pixmap.set_dpi(300, 300)
        pixmap.save(QA / (name + ".embedded_170mm.png"))
    run_audit("audit_pdf_text.py", [str(FIG / (name + ".pdf")), "--min-pt", "5", "--json"],
              QA / (name + ".text.log"))
    run_audit("audit_figure_collisions.py", [str(FIG / (name + ".pdf")),
              "--json-out", str(QA / (name + ".collision.json")),
              "--overlay-pdf", str(QA / (name + ".collision_overlay.pdf"))],
              QA / (name + ".collision.log"))
    CHECKS.append({"figure": number, "alignment": alignment.get("verdict", alignment.get("status", "see JSON")),
                   "pdf_text": "PASS", "collision": "PASS", "visual_review": "PENDING",
                   "source_rows": SOURCES[number][2],
                   "pdf_sha256": sha(FIG / (name + ".pdf")),
                   "preview_sha256": sha(QA / (name + ".final_size.png"))})
    plt.close(fig)


def error_points(ax, d, ys):
    x = d.percent_estimate.to_numpy()
    lower = d.percent_CI_lower.to_numpy()
    upper = d.percent_CI_upper.to_numpy()
    assert np.all(lower <= x) and np.all(x <= upper)
    ec = ax.errorbar(x, ys, xerr=np.vstack([x - lower, upper - x]), fmt="o", ms=4,
                    color=BLUE, elinewidth=1, capsize=2, zorder=3)
    segments = ec[2][0].get_segments()
    assert len(segments) == len(d)
    for segment, lo, hi in zip(segments, lower, upper):
        assert np.allclose(segment[:, 0], [lo, hi], rtol=0, atol=1e-12)


def forest(number):
    d = read_source(number)
    lo, hi = d.percent_CI_lower.min(), d.percent_CI_upper.max()
    pad = (hi - lo) * 0.10
    fig = plt.figure(figsize=(183 / 25.4, 210 / 25.4))
    panel_axes = []
    for j, oid in enumerate(IDS):
        row, column = divmod(j, 2)
        ax = axes(fig, [31 + 92 * column, 151 - 65 * row, 53, 43], chr(97 + j))
        panel_axes.append(ax)
        one = d[d.outcome_id.eq(oid)].copy()
        if number == 4:
            one = one.sort_values("ses_sd")
            labels = [f"{value:+g} SD" if value else "0 SD" for value in one.ses_sd]
        elif number == 6:
            labels = [{"full": "Full", "drop2020": "No 2020", "dropCA": "No CA",
                       "dropCA_and2020": "No CA or 2020", "dropCA2020only": "No CA in 2020"}[m]
                      for m in one.model_id]
        elif number == 7:
            labels = [m.replace("_relaxed_", " r ").replace("_strict_", " s ")
                      .replace("noLST", "−L").replace("withLST", "+L")
                      for m in one.model_id]
        else:
            labels = list(one.model_id)
            assert one.n_county_years.eq(3062).all()
        error_points(ax, one, np.arange(len(one)))
        ax.axvline(0, color="#879299", ls="--", lw=0.8, zorder=0)
        ax.set(yticks=range(len(labels)), yticklabels=labels,
               ylim=(len(labels) - 0.45, -0.6), xlim=(lo - pad, hi + pad),
               xlabel="Conditional association (%)" if number == 4 else "Interaction: RRR change (%)")
        ax.tick_params(axis="y", length=0, pad=5)
        ax.spines["left"].set_visible(False)
        title(ax, chr(97 + j), LABELS[j])
    note = "Ordinary 95% confidence intervals\n30 allocated datasets per fit\nFixed smoke IQR and disadvantage scale\n2009–2020 study window"
    if number == 7:
        note += "\nr / s: relaxed / strict QA\n−L / +L: without / with LST"
    fig.text(123 / 183, 27 / 210, note, fontsize=7.0, linespacing=1.8)
    save(fig, number, panel_axes, rows=[["a", "b"], ["c", "d"]],
         cols=[["a", "c", "e"], ["b", "d"]])


def heatmap():
    d = read_source(1)
    matrix = d.pivot(index="state_abbr", columns="year", values="population_weighted_smoke").loc[SIX]
    assert matrix.shape == (6, 12) and np.isfinite(matrix.to_numpy()).all()
    fig = plt.figure(figsize=(183 / 25.4, 85 / 25.4))
    ax = axes(fig, [17, 24, 137, 47], "a")
    im = ax.imshow(matrix, aspect="auto", cmap="YlOrBr", vmin=0, vmax=np.ceil(matrix.to_numpy().max()))
    ax.set(yticks=range(6), yticklabels=SIX, xticks=range(12),
           xticklabels=range(2009, 2021), xlabel="Year")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    title(ax, "a", "Annual county-population-weighted state smoke")
    colorbar = fig.colorbar(im, cax=axes(fig, [161, 24, 3, 47], "colourbar"))
    colorbar.set_label("Smoke PM2.5 (μg/m³)")
    colorbar.solids.set_rasterized(False)
    colorbar.solids.set_edgecolor("face")
    save(fig, 1, [ax])


def county_distribution():
    d = read_source(2).sort_values("county_fips")
    assert d.county_fips.nunique() == 256
    values = [d.loc[d.state_abbr.eq(state), "smoke_mean"].to_numpy() for state in SIX]
    assert [len(value) for value in values] == [15, 58, 64, 44, 36, 39]
    fig = plt.figure(figsize=(183 / 25.4, 105 / 25.4))
    ax = axes(fig, [20, 24, 154, 68], "a")
    ax.boxplot(values, showfliers=False, widths=0.5, patch_artist=True,
               medianprops={"color": BLACK}, boxprops={"facecolor": "#F0F4F6"})
    for j, value in enumerate(values, 1):
        # All points appear; deterministic horizontal offset only avoids overplotting.
        offset = 0.2 * np.sin(np.arange(len(value)) * 2.3999632297)
        ax.scatter(j + offset, value, s=9, color=BLUE, alpha=0.7, zorder=3)
        ax.scatter([j], [value.mean()], s=26, color=ORANGE, marker="D", zorder=5)
    ax.set(xticks=range(1, 7), xticklabels=[f"{s}\nn={len(v)}" for s, v in zip(SIX, values)],
           ylabel="County mean smoke, 2009–2020 (μg/m³)", ylim=(0, 2.8))
    title(ax, "a", "Within-state county exposure distributions")
    ax.legend(handles=[Line2D([], [], marker="D", color=ORANGE, ls="none", label="Mean"),
                       Line2D([], [], color=BLACK, label="Median")], loc="upper right", ncol=2)
    save(fig, 2, [ax])


def nesting():
    d = read_source(3)
    assert d.n_county_years.eq(3072).all() and d.n_draw_comparisons.eq(92160).all()
    labels = [value.replace(" subset ", " > ") for value in d.relation]
    y = np.arange(len(d))
    fig = plt.figure(figsize=(183 / 25.4, 90 / 25.4))
    a = axes(fig, [34, 21, 53, 52], "a")
    b = axes(fig, [125, 21, 51, 52], "b")
    a.barh(y, d.draw_violations, color=BLUE, height=0.5)
    a.set(yticks=y, yticklabels=labels, ylim=(2.6, -0.6),
          xlabel="Child > parent comparisons", xlim=(0, 11000))
    a.tick_params(axis="y", length=0)
    title(a, "a", "92,160 comparisons per relation")
    for yy, value in zip(y, d.draw_violations):
        a.text(value + 100, yy, f"{value:,}", va="center", fontsize=7)
    b.barh(y - 0.17, d.any_draw_violations, color=BLUE, height=0.3, label="Any allocation")
    b.barh(y + 0.17, d.mean_count_violations, color=ORANGE, height=0.3, label="Mean count")
    b.set(yticks=y, yticklabels=labels, ylim=(2.6, -0.6), xlabel="County–years", xlim=(0, 950))
    b.tick_params(axis="y", length=0)
    title(b, "b", "3,072 county–years per relation")
    b.legend(loc="lower left", bbox_to_anchor=(-0.12, -0.33), ncol=2,
             fontsize=7, handlelength=1.2, columnspacing=0.8)
    save(fig, 3, [a, b], rows=[["a", "b"]])


def main():
    # The root task must issue the document/PDF artifact marker before invoking.
    run_audit("validate_figure.py", [str(Path(__file__).resolve()), "--json"], QA / "source_validation.json")
    heatmap()
    county_distribution()
    nesting()
    for number in range(4, 8):
        forest(number)
    pd.DataFrame(MAP).to_csv(ROOT / "audit/figure_source_data_map.csv", index=False)
    pd.DataFrame(CHECKS).to_csv(ROOT / "audit/figure_automated_checks.csv", index=False)
    for row in MANIFEST:
        row["sha256_after"] = sha(row["path"])
        row["status"] = "PASS" if row["sha256_before"] == row["sha256_after"] else "FAIL"
        assert row["status"] == "PASS"
    pd.DataFrame(MANIFEST).to_csv(ROOT / "audit/figure_input_hash_check.csv", index=False)
    print("Seven figures rendered; final visual review remains a separate required step.", flush=True)


if __name__ == "__main__":
    main()
