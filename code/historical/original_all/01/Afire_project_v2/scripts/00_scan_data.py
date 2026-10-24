from afire_pipeline import ensure_dirs, scan_data, scan_other_health


if __name__ == "__main__":
    ensure_dirs()
    scan_data()
    scan_other_health()
