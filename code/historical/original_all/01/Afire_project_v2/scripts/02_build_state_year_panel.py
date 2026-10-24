from afire_pipeline import ensure_dirs, build_panel, missing_report


if __name__ == "__main__":
    ensure_dirs()
    panel = build_panel()
    missing_report(panel)
