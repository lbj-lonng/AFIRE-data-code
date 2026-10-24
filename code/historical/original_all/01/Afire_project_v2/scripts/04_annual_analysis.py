import pandas as pd

from afire_pipeline import DIRS, annual_analysis, ensure_dirs


if __name__ == "__main__":
    ensure_dirs()
    panel = pd.read_csv(DIRS["processed"] / "state_year_disease_panel.csv")
    annual_analysis(panel)
