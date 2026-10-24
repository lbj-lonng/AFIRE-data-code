from afire_pipeline import ensure_dirs, build_pm25_state_year, build_fire_state_year


if __name__ == "__main__":
    ensure_dirs()
    exposure = build_pm25_state_year()
    build_fire_state_year(exposure)
