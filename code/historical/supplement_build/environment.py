"""Task-local manuscript environment; never imports a previous builder."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "submission"
AUD = ROOT / "audit"
SD = SUB / "source_data"
BASE = ROOT.parent / "AFIRE_2009_2020_five_outcomes_20260915_194616"
sys.dont_write_bytecode = True
for directory in (SUB, AUD, SD, AUD / "tmp", AUD / "render", AUD / "mpl", SUB / "supplementary_data", SD / "tables"):
    directory.mkdir(parents=True, exist_ok=True)
for key in ("TEMP", "TMP", "TMPDIR"):
    os.environ[key] = str(AUD / "tmp")
os.environ["MPLCONFIGDIR"] = str(AUD / "mpl")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
# Reuse the existing task-managed scientific dependencies read-only.
sys.path.extend([
    "C:/Users/86189/Documents/Codex/2026-09-10/ban/work/pydeps",
    "D:/postgraduate/wildfire/9.10/AFIRE_threepart_mainfig_redesign_20260912_173900/_work/deps",
    "D:/postgraduate/wildfire/9.10/9.15/AFIRE_manuscript_figures_integrated_20260915_170300/_work/mathdeps",
])
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
