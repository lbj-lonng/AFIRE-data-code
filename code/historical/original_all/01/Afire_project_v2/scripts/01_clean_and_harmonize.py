from afire_pipeline import ensure_dirs, build_pm25_state_year, build_ses_state_year, load_cdc_health, scan_other_health


if __name__ == "__main__":
    ensure_dirs()
    scan_other_health()
    build_pm25_state_year()
    build_ses_state_year()
    load_cdc_health()
