"""Record completed human-like visual inspection of all final English pages.

This script records observations made after actual view_image calls; it does not
perform or claim automated visual inspection. Re-rendering invalidates this log.
"""
from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "audit/render/Supplementary_Information_EN"
DOCX = ROOT / "submission/Supplementary_Information_EN.docx"
EXPECTED_DOCX_SHA256 = "36d7b6226be884a7222143fac940737eaefa743c4a6a123a5f627ecef2b9df80"

OBSERVATIONS = {
    1: "Title, scope, Methods 1 and start of Methods 2 fit within margins; Equation 1 and its superscripts/fractions are readable; footer unobstructed.",
    2: "Equation 2 is complete; geographical weighting and fire-catalogue text are readable; heading/paragraph transitions and footer have no overlap.",
    3: "Methods 4 and Equations 3-6 are complete and readable; finite-support constraints, sums, fractions and accents render without clipped glyphs.",
    4: "Methods 5-6 and Equations 7-8 render fully; long explanatory paragraphs and equation brackets remain inside margins.",
    5: "Equations 9-12, pooling and conditional-contrast text are readable; lower paragraph continues normally to next page without clipping.",
    6: "Continuation from Methods 7, Notes 1-4 and units render correctly; final paragraph continues normally; no orphan heading or overlap.",
    7: "Continuation of Note 4, Notes 5-6 and Discussion are complete and readable; section transitions and footer clear.",
    8: "Former blank page is eliminated. Tables 1-2 begin with aligned headers; 11 variable rows readable; Table 2 continues with final LST row on page 9.",
    9: "Table 2 repeats its header for final LST row. Tables 3-4 and first Table 5 rows are aligned; units, counts and percentile headers readable.",
    10: "Table 5 continuation has repeated header. Tables 6-7 and first Table 8 rows fit; state labels, assignment counts and percentages not clipped.",
    11: "Table 8 continuation and full Table 9 are readable; Table 10 heading/note retained with header and first rows; numeric columns remain distinct.",
    12: "Table 10 continues with repeated header; Tables 11-12 and diagnostic denominators visible; widest header stays within the table.",
    13: "Tables 13-15 and start of Table 16 readable; alpha, seeds, model names, CI bounds and original 7-test Holm label visible; continuation is intentional.",
    14: "Table 16 continuation repeats header and retains all visible negative/zero-crossing intervals; Table 17 begins with full note and clear numeric columns.",
    15: "Table 17 continuation repeats header; Table 18 note distinguishes joint omission from CA-only-in-2020; rows and columns remain aligned.",
    16: "Table 18 continuation includes the negative IHD point estimates and full CI strings. Table 19 heading, note and first rows are readable.",
    17: "Table 19 continuation, Table 20 and start of Table 21 readable; historical model-definition note is not truncated; full-width columns fit.",
    18: "Table 21 continuation and complete Table 22 are aligned and readable. Remaining whitespace marks the end of tables before dedicated figure pages, not a blank page.",
    19: "Supplementary Fig. 1 heatmap and complete caption are on one page; state/year labels, colour bar and concentration units legible and uncropped.",
    20: "Supplementary Fig. 2 boxplots, all state labels/counts and legend readable; extreme county points visible; complete caption on same page.",
    21: "Supplementary Fig. 3 panels a-b, counts, axes and legend readable; both bars/diagnostic views uncropped; full explanatory caption on same page.",
    22: "Supplementary Fig. 4 all five outcome panels, 25 intervals and zero-reference lines visible; axis labels and complete caption legible.",
    23: "Supplementary Fig. 5 all five panels and eight model labels per panel fit; CI whiskers are not clipped; complete caption remains on page.",
    24: "Supplementary Fig. 6 all omission labels readable, including no CA or 2020 versus no CA in 2020; widest IHD interval is completely shown; caption complete.",
    25: "Supplementary Fig. 7 all five panels and strict/relaxed paired labels visible; intervals and explanatory key readable; complete caption within margins.",
    26: "All 12 supplementary references and URLs remain readable inside margins; line wraps are ordinary and no citation or footer is clipped.",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    actual_docx_sha = sha256(DOCX)
    if actual_docx_sha != EXPECTED_DOCX_SHA256:
        raise RuntimeError("Final English DOCX changed after the instructed visual-review revision")
    page_paths = list(RENDER.glob("page-*.png"))
    if len(page_paths) != 26 or set(OBSERVATIONS) != set(range(1, 27)):
        raise RuntimeError("Expected exactly the 26 actually inspected page images")
    output = ROOT / "audit/visual_review_EN.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["page", "page_image", "sha256", "inspection", "status", "observation"])
        writer.writeheader()
        for page in range(1, 27):
            path = RENDER / f"page-{page}.png"
            writer.writerow({
                "page": page,
                "page_image": str(path),
                "sha256": sha256(path),
                "inspection": "Actually viewed the complete original page PNG using view_image(detail=original); not thumbnail or automated-only inspection",
                "status": "PASS",
                "observation": OBSERVATIONS[page],
            })
    metadata = {
        "reviewer": "/root/si_numerical",
        "review_recorded_utc": datetime.now(timezone.utc).isoformat(),
        "docx": str(DOCX),
        "docx_sha256": actual_docx_sha,
        "pages_actually_viewed": 26,
        "page_range": "1-26, every page",
        "blocking_visual_findings": 0,
        "visual_log": str(output),
        "limitations": "Visual review is not independent scientific validation or OCR; cell and source validation are recorded separately. A changed DOCX or page image invalidates its associated review hash.",
    }
    (ROOT / "audit/visual_review_EN_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
