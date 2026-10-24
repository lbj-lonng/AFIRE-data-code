import pandas as pd

from afire_pipeline import DIRS, ensure_dirs, run_models


if __name__ == "__main__":
    ensure_dirs()
    panel = pd.read_csv(DIRS["processed"] / "state_year_disease_panel.csv")
    run_models(panel)
