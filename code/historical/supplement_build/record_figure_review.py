"""Seal a genuinely inspected figure render, rejecting any changed image.

Run only after reviewing the embedded-width PNGs. The expected hashes refer to
the render personally inspected in this task; new renders require renewed
inspection and a consciously updated record, not automatic inherited approval.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "audit/figures"
EXPECTED = {
    1: "f93f80273f1f1c155961e2bfac589b81c6a9a5fd520fc8546c70b2b58d842848",
    2: "d0dcdf514fdb32c86137849c6dbfb09629b8a02435e0449ff259276181e0143a",
    3: "430256d4e2fd6581e07add8d7e84501271c2cbfcaff68f816ff76f4cc5a3a426",
    4: "52d4674553ceb00b76401f3886798090ed24ad0b879148b5362fd8150e382007",
    5: "0ab69cb82413811389786a4602a100c03ae23edc317f67c17643dd73f9ff6765",
    6: "c449a827c57648a7d1867c7176a14dab42e34774a31736b3892f40860bd6d203",
    7: "e4df321b01e67e45eeabf4fe293c6857dec3f9648cb12e1b90876f93f6657959",
}
DETAILS = {
    1: ("Annual context", "County-population-weighted annual smoke", "None: descriptive means", "72 state–years", "All 72 cells and 12 years visible; sequential color scale has no PDF seams; colorbar not part of comparable-panel alignment."),
    2: ("Within-state heterogeneity", "Every county point plus median/quartiles and equal-weight mean", "Box quartiles and 1.5-IQR whiskers, not CI", "256 counties", "Every county included; values beyond boxplot whiskers remain explicit blue points; mean and median distinguished by shape."),
    3: ("Parent-child inconsistency boundary", "Raw inconsistency counts", "None: array diagnostic", "3 relations", "a and b aligned at top/bottom; counts 9127/3197/506 preserved; counts not interpreted as joint-posterior probabilities."),
    4: ("Conditional association boundary", "Saved conditional rate-ratio percentage", "Ordinary two-sided 95% CI", "5 contrasts per outcome", "All 25 contrasts retain full lower/upper limits; negative and zero-crossing intervals are visible; common x-axis."),
    5: ("Common-sample specification sensitivity", "Saved interaction RRR percentage", "Ordinary two-sided 95% CI", "8 models per outcome; 3062 county–years", "All 40 C-block estimates displayed, same sample and complete intervals; model names and panel axes aligned."),
    6: ("Targeted omission boundary", "Saved interaction RRR percentage", "Ordinary two-sided 95% CI", "5 specifications per outcome", "All 25 estimates; largest negative IHD limit is visible without clipping; no claim of formal model-difference testing."),
    7: ("Within-branch LST adjustment boundary", "Saved interaction RRR percentage", "Ordinary two-sided 95% CI", "8 branch/model rows per outcome", "All 40 estimates, including strict-branch zero-crossing limits; r/s and −L/+L keys visible; no paired-difference inference added."),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-current-render-inspected", action="store_true", required=True)
    parser.parse_args()
    reviews, panel_reviews = [], []
    for n, expected in EXPECTED.items():
        name = f"Supplementary_Figure_{n}"
        assert sha(QA / (name + ".final_size.png")) == expected, "Render changed; inspect before sealing"
        collision = json.loads((QA / (name + ".collision.json")).read_text(encoding="utf-8"))
        alignment = json.loads((QA / (name + ".alignment.json")).read_text(encoding="utf-8"))
        text = json.loads((QA / (name + ".text.log")).read_text(encoding="utf-8"))
        assert collision["verdict"] == "PASS" and collision["summary"]["fail"] == 0
        assert collision["summary"]["warn"] == 0
        assert alignment["verdict"] in ("PASS", "NOT APPLICABLE")
        assert text["minimum_found_pt"] * 170 / 183 >= 5
        review = {
            "figure": n, "reviewed_image": str((QA / (name + ".embedded_170mm.png")).relative_to(ROOT)),
            "reviewed_image_sha256": sha(QA / (name + ".embedded_170mm.png")),
            "final_preview_sha256": expected,
            "pdf_sha256": sha(ROOT / "submission/figures" / (name + ".pdf")),
            "embedding_width_mm": 170, "minimum_scaled_glyph_pt": text["minimum_found_pt"] * 170 / 183,
            "alignment": alignment["verdict"], "collision": "PASS", "pdf_text": "PASS",
            "status": "PASS", "visual_notes": DETAILS[n][4],
        }
        reviews.append(review)
        letters = "a" if n < 3 else "ab" if n == 3 else "abcde"
        for index, letter in enumerate(letters):
            panel_reviews.append({
                "figure": n, "panel": letter,
                "stratum": ("COPD", "CLRD", "RESP", "CIRC", "IHD")[index] if n >= 4 else "Not applicable",
                "unique_claim": DETAILS[n][0], "center_or_summary": DETAILS[n][1],
                "spread_or_interval": DETAILS[n][2], "record_unit": DETAILS[n][3],
                "labels_and_legend": "Readable; five-outcome scope; no clipped endpoint",
                "alignment": alignment["verdict"], "collision": "PASS (0 fail; 0 warn)",
                "uncertainty_geometry": "Saved endpoints checked numerically against plotted segments" if n >= 4 else "Descriptive only; no invented inference",
                "status": "PASS", "notes": DETAILS[n][4],
            })
    write_csv(ROOT / "audit/figure_visual_review.csv", reviews)
    write_csv(ROOT / "audit/figure_panel_review.csv", panel_reviews)
    path = ROOT / "audit/figure_automated_checks.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        checks = list(csv.DictReader(handle))
    for row in checks:
        row["visual_review"] = "PASS"
    write_csv(path, checks)
    print("Seven figure-level and 24 panel-level visual review records sealed.")


if __name__ == "__main__":
    main()
