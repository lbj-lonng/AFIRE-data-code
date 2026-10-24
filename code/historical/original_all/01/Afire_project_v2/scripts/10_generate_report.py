import pandas as pd

from afire_pipeline import DIRS, ensure_dirs, scan_data, write_readme, write_report


if __name__ == "__main__":
    ensure_dirs()
    inventory = scan_data()
    panel = pd.read_csv(DIRS["processed"] / "state_year_disease_panel.csv")
    annual_exp = pd.read_csv(DIRS["tables"] / "annual_exposure_inequality.csv")
    annual_health = pd.read_csv(DIRS["tables"] / "annual_health_inequality_by_disease.csv")
    model_results = pd.read_csv(DIRS["tables"] / "disease_specific_model_results.csv")
    fire_comp = pd.read_csv(DIRS["tables"] / "fire_vs_nonfire_comparison.csv")
    wph = pd.read_csv(DIRS["tables"] / "WPHII_state_year_disease.csv")
    sens = pd.read_csv(DIRS["tables"] / "sensitivity_analysis.csv")
    write_report(inventory, panel, annual_exp, annual_health, model_results, fire_comp, wph, sens)
    write_readme()
