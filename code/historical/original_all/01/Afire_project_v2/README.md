# Afire Project

This folder contains a reproducible state-scale wildfire PM2.5 and health inequity analysis package.

## Data

Raw data are read from:

`/home/yyy/zhou/health/Afire`

Raw files are not modified.

## Run

Use the bundled Codex Python used during generation:

```powershell
& 'C:\Users\86189\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\scripts\run_all.py
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
