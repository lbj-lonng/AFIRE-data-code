import pandas as pd

from afire_pipeline import DIRS, annual_analysis, ensure_dirs, figures, run_models, wphii


if __name__ == "__main__":
    ensure_dirs()
    panel = pd.read_csv(DIRS["processed"] / "state_year_disease_panel.csv")
    annual_exp, annual_health = annual_analysis(panel)
    model_results, _ = run_models(panel)
    wph = wphii(panel)
    figures(panel, annual_exp, annual_health, model_results, wph)
