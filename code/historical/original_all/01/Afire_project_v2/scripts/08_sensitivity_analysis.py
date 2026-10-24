import pandas as pd

from afire_pipeline import DIRS, ensure_dirs, run_models, sensitivity


if __name__ == "__main__":
    ensure_dirs()
    panel = pd.read_csv(DIRS["processed"] / "state_year_disease_panel.csv")
    _, model_panel = run_models(panel)
    sensitivity(panel, model_panel)
