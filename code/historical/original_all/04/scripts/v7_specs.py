from __future__ import annotations

from v7_common import ModelSpec

STATES = ("AZ", "CA", "CO", "ID", "OR", "WA")
BASE_TERMS = ("pm25_iqr", "pm25_iqr:ses_baseline_std")


def spec(
    model_id: str,
    label: str,
    group: str,
    rhs: str,
    required: tuple[str, ...],
    year_min: int,
    year_max: int,
    *,
    cause_id: str = "copd",
    family: str = "negative_binomial",
    exposure_term: str = "pm25_iqr",
    interaction_term: str = "pm25_iqr:ses_baseline_std",
    include_states: tuple[str, ...] = (),
    exclude_states: tuple[str, ...] = (),
    exclude_years: tuple[int, ...] = (),
    min_rows: int = 500,
    min_counties: int = 30,
    notes: str = "",
) -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        label=label,
        group=group,
        cause_id=cause_id,
        family=family,
        rhs=rhs,
        exposure_term=exposure_term,
        interaction_term=interaction_term,
        required=required,
        year_min=year_min,
        year_max=year_max,
        include_states=include_states,
        exclude_states=exclude_states,
        exclude_years=exclude_years,
        min_rows=min_rows,
        min_counties=min_counties,
        notes=notes,
    )


CORE_SPECS = [
    spec(
        "O01_baseline_SES_fixed_2006_2020", "基础固定SES模型", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std"), 2006, 2020,
    ),
    spec(
        "O02_Census_adjusted_2009_2020", "Census调整模型", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7"), 2009, 2020,
    ),
    spec(
        "O03_state_year_PPML_2009_2020", "州×年份固定效应PPML", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + C(county_model) + C(state_year)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7"), 2009, 2020,
        family="poisson", notes="使用Poisson伪最大似然替代不稳定的高维负二项IRLS。",
    ),
    spec(
        "O04_drought_adjusted_2009_2020", "Census与干旱调整", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2009, 2020,
    ),
    spec(
        "O05_exclude_2020_drought", "剔除2020年的干旱调整", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2009, 2019,
    ),
    spec(
        "O06_timevarying_SES_2010_2020", "时变SES敏感性", "core",
        "pm25_iqr + ses_timevarying_std + pm25_iqr:ses_timevarying_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_timevarying_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2010, 2020,
        interaction_term="pm25_iqr:ses_timevarying_std",
    ),
    spec(
        "O07_lag1_2010_2020", "滞后一年暴露", "core",
        "pm25_lag1_iqr + pm25_lag1_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_lag1_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2010, 2020,
        exposure_term="pm25_lag1_iqr", interaction_term="pm25_lag1_iqr:ses_baseline_std",
    ),
    spec(
        "O08_lead1_placebo_2009_2019", "提前一年安慰剂", "core",
        "pm25_lead1_iqr + pm25_lead1_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_lead1_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2009, 2019,
        exposure_term="pm25_lead1_iqr", interaction_term="pm25_lead1_iqr:ses_baseline_std",
    ),
    spec(
        "O09_three_state_air_2009_2020", "ID/OR/WA空气污染敏感性", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + pm25_total_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "pm25_total_std_v7", "ozone_std_v7"), 2009, 2020,
        include_states=("ID", "OR", "WA"), min_rows=1000, min_counties=80,
    ),
    spec(
        "O10_temperature_adjusted_2009_2020", "温度调整主模型", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"), 2009, 2020,
    ),
    spec(
        "O11_full_environment_2009_2020", "六州完全环境调整", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + pm25_total_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "pm25_total_std_v7", "ozone_std_v7"), 2009, 2020,
        notes="总PM2.5包含野火成分，因此仅作为敏感性模型。",
    ),
    spec(
        "O12_smoking_2018_2020", "吸烟率敏感性", "core",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + smoking_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "smoking_std_v7"), 2018, 2020,
        min_rows=700, min_counties=200,
    ),
]

FINAL_COMPLEMENT = [
    spec(
        "F01_temperature_exclude_2020", "温度调整并剔除2020", "final",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"), 2009, 2019,
    ),
    spec(
        "F02_full_environment_exclude_2020", "完全环境调整并剔除2020", "final",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + pm25_total_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "pm25_total_std_v7", "ozone_std_v7"), 2009, 2019,
    ),
    spec(
        "F03_nonwildfire_PM25_2009_2020", "非野火PM2.5调整", "final",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + nonwildfire_pm25_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "nonwildfire_pm25_std_v7", "ozone_std_v7"), 2009, 2020,
        notes="仅在非野火PM2.5覆盖率≥95%且负值比例≤1%时运行。",
    ),
    spec(
        "F04_nonwildfire_PM25_exclude_2020", "非野火PM2.5调整并剔除2020", "final",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + nonwildfire_pm25_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "nonwildfire_pm25_std_v7", "ozone_std_v7"), 2009, 2019,
    ),
    spec(
        "F05_poverty_modifier_2009_2020", "贫困率效应修饰", "final",
        "pm25_iqr + pm25_iqr:poverty_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "poverty_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"), 2009, 2020,
        interaction_term="pm25_iqr:poverty_baseline_std",
    ),
    spec(
        "F06_period_2009_2016", "较早时期2009–2016", "final",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"), 2009, 2016,
    ),
    spec(
        "F07_period_2017_2020", "近期高烟雾时期2017–2020", "final",
        "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
        ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"), 2017, 2020,
        min_rows=900, min_counties=200,
    ),
]


def leave_one_year_specs() -> list[ModelSpec]:
    out = []
    for year in range(2009, 2021):
        out.append(spec(
            f"Y{year}_leave_out", f"剔除{year}年", "leave_one_year",
            "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
            ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"),
            2009, 2020, exclude_years=(year,), notes=f"温度调整主模型剔除{year}年。"
        ))
    return out


def leave_one_state_specs() -> list[ModelSpec]:
    out = []
    for state in STATES:
        out.append(spec(
            f"L{state}_leave_out", f"剔除{state}", "leave_one_state",
            "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
            ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"),
            2009, 2020, exclude_states=(state,), min_rows=1500, min_counties=150,
        ))
    return out


def state_specific_specs() -> list[ModelSpec]:
    out = []
    for state in STATES:
        out.append(spec(
            f"S{state}_specific", f"{state}州分层模型", "state_specific",
            "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
            ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"),
            2009, 2020, include_states=(state,), min_rows=150, min_counties=10,
            notes="州分层结果为异质性探索；县聚类数较少的州需谨慎解释。",
        ))
    return out


def secondary_outcome_specs() -> list[ModelSpec]:
    causes = {
        "respiratory_system": "呼吸系统疾病",
        "chronic_lower_respiratory": "慢性下呼吸道疾病",
        "asthma": "哮喘",
        "circulatory_system": "循环系统疾病",
        "ischemic_heart_disease": "缺血性心脏病",
        "cerebrovascular_disease": "脑血管疾病",
    }
    out = []
    for cause, label in causes.items():
        out.append(spec(
            f"D_{cause}", label, "secondary_outcomes",
            "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)",
            ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"),
            2009, 2020, cause_id=cause,
        ))
    return out


ALL_SPECS = CORE_SPECS + FINAL_COMPLEMENT + leave_one_year_specs() + leave_one_state_specs() + state_specific_specs() + secondary_outcome_specs()
SPEC_BY_ID = {s.model_id: s for s in ALL_SPECS}

ESSENTIAL_FINAL_IDS = {
    "O03_state_year_PPML_2009_2020",
    "O10_temperature_adjusted_2009_2020",
    "O11_full_environment_2009_2020",
    *[s.model_id for s in FINAL_COMPLEMENT],
    *[s.model_id for s in leave_one_year_specs()],
    *[s.model_id for s in leave_one_state_specs()],
    *[s.model_id for s in state_specific_specs()],
    *[s.model_id for s in secondary_outcome_specs()],
}
