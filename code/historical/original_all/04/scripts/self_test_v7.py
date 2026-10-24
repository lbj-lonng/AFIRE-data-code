from __future__ import annotations

import numpy as np
import pandas as pd

from v7_common import rubin_pool
from v7_engine import build_design
from v7_specs import SPEC_BY_ID


def main() -> None:
    pooled = rubin_pool([0.1, 0.11, 0.09], [0.01, 0.01, 0.01])
    assert np.isfinite(pooled["estimate"])
    assert pooled["m_used"] == 3

    # Synthetic nested FE design: county FE + state×year FE is intentionally
    # rank-deficient before alias removal. The target terms must be retained.
    rows = []
    county = 0
    for state in ["AZ", "CA"]:
        for _ in range(3):
            county += 1
            for year in [2019, 2020]:
                rows.append({
                    "county_model": str(county),
                    "state_year": f"{state}_{year}",
                    "pm25_iqr": 0.1 * county + 0.03 * year,
                    "ses_baseline_std": -1 + county / 3,
                    "age65_std_v7": county / 10,
                    "density_std_v7": year / 2020,
                })
    frame = pd.DataFrame(rows)
    spec = SPEC_BY_ID["O03_state_year_PPML_2009_2020"]
    reduced, design, names, indices = build_design(frame, spec)
    assert design.shape[1] == np.linalg.matrix_rank(design)
    assert spec.exposure_term in names
    assert spec.interaction_term in names
    print("v7 self-test passed")


if __name__ == "__main__":
    main()
