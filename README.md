# AFIRE data and code — version 2026.10.24

This release supports the 2009–2020 wildfire-smoke exposure and mortality manuscript:
256 counties in AZ, CA, CO, ID, OR and WA; five reported mortality outcomes; four main
figures and Supplementary Figs. S1–S10. It combines frozen Source Data with archived
original and subsequently extended implementations. It does not introduce new model fits.

## Availability and version

The analysis snapshot used for the availability statements is commit
`ab380fca168a4e2cc025cbad31fb10db7da8903b`. See `AVAILABILITY_STATEMENTS_EN.txt` for
current manuscript wording and `metadata/publication_record.json` for the verified
public-access record. A GitHub commit identifies a version; it is not a DOI.

## Download and inspect

Use **Code → Download ZIP** and extract the downloaded repository, or clone it:

```sh
git clone https://github.com/lbj-lonng/AFIRE-data-code.git
cd AFIRE-data-code
```

The repository contains:

| Location | Contents |
|---|---|
| `data/source_data/full_results/` | 135 full-precision stored health estimates; exposure, mortality reporting status and matched validation records |
| `data/source_data/Figure_1/`–`Figure_4/` | Main-figure panel source tables |
| `data/source_data/figures/` | Supplementary Figs. S1–S7 source tables |
| `data/supplementary_figures_S8_S10/` | Supplementary Figs. S8–S10 source tables and display definitions |
| `data/source_data/tables/` | Supplementary Tables 1–22, including links to unrounded exports |
| `data/supplementary_data/` | Supplementary Data 1–3 and their original descriptions |
| `data/source_data/geography/` | Frozen display geometries and archived Census boundary products |
| `data/Supplementary_References.bib` | Verified original-source bibliographic records |
| `code/historical/original_all/01`–`04` | Code from the original `Afire/all` experimental project |
| `code/historical/B1_joint_adjustment/` | B1 unified imputation and joint environmental-adjustment implementation |
| `code/historical/seven_outcome_extension/` | Later seven-outcome extension, frozen protocol and code snapshot |
| `code/historical/main_figure_build/`, `supplement_build/`, `S8_S10_build/` | Existing figure/manuscript assembly implementations |
| `reference_figures/` | Frozen PDF/SVG figures for comparison |
| `metadata/` | Scope, provenance, variable dictionary and known limitations |

Main historical source files are retained byte-for-byte; `metadata/source_provenance.csv`
records their origin and hashes. Historical code may contain original machine-specific
paths. It must not be executed indiscriminately against the original project.

## Verify the release

Python 3.10 or newer; verification uses only the standard library:

```sh
cd AFIRE-data-code
python verify_release.py
```

`SHA256SUMS.csv` authenticates every release payload file. It excludes itself and ignored
outputs. The verifier checks identities of saved data; this is not a raw-source replication.

## Rebuild figures from frozen results

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your operating system.
python -m pip install -r requirements-figures.txt
python reproduce_figures.py --output outputs/rebuild_01 --figures all
```

The output directory must be new. Select `main`, `supplement`, or `extra` to reproduce
only that group. The adapter stages copies, replaces paths only in those copies, and
runs the preserved plotting scripts. Outputs include four main and ten supplementary
figures. This entry point does not refit mortality models, regenerate allocations or
recompute statistical significance. Font availability can change typography; compare
regenerated figures with `reference_figures/` before submission.

## Scientific and access boundaries

The five reported outcomes are COPD, chronic lower respiratory diseases, respiratory-system
diseases, circulatory-system diseases and ischaemic heart disease. They overlap and are not
additive. The original seven-test Holm family is retained. Seven-outcome code is historical
evidence and does not silently replace the current five-outcome results.

Public mortality records retain suppressed counts as missing, distinct from zero. Individual
allocation arrays and reconstructed suppressed county counts are omitted from this release.
They are model-generated plausible values, not observed hidden deaths. The public release
supports inspection and replotting of saved results, **not an unrestricted end-to-end refit**.
The author-only backup is separate and is not included in this repository.

An audit of historical code and inputs is in `metadata/REPRODUCIBILITY_AND_GAPS.txt`.
Exact upstream extraction versions, some covariate build records and the full fire-catalogue
ranking/deduplication history remain incomplete. Provider documentation is not proof of the
identity of an unavailable historical download. Original data use conditions apply; consult
`RIGHTS_AND_ACCESS.txt`. A software licence and a DOI archive have not been assigned by
this packaging step.

## Original data routes

Mortality and population: [CDC WONDER](https://wonder.cdc.gov/), subject to its
[data-use restrictions](https://wonder.cdc.gov/datause.html).
Socioeconomic and demographic sources: [IPUMS NHGIS](https://www.nhgis.org/) and
[American Community Survey](https://www.census.gov/programs-surveys/acs).
Wildfire smoke: Childs et al., [doi:10.1021/acs.est.2c02934](https://doi.org/10.1021/acs.est.2c02934).
Daytime LST: MOD11A2.061, [doi:10.5067/MODIS/MOD11A2.061](https://doi.org/10.5067/MODIS/MOD11A2.061).
Additional environmental, fire and geographic source identities are documented in the
Supplementary Information and `data/Supplementary_References.bib`; unresolved versions
are explicitly retained in the metadata.


## Source documentation update

Supplementary Table S2 source/version metadata were refined on 24 October 2026.
See `metadata/source_documentation_update_20261024/README.txt` for the resolved
ACS and NOAA records, numerical identity checks and remaining historical metadata gaps.
The underlying numerical analysis is unchanged.
