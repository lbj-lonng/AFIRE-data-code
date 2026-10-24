# Socioeconomic disadvantage alters the association between wildfire smoke and mortality in 256 western US counties

## Supplementary Information

This Supplement supports the two questions in the main text: exposure distributions and socioeconomic context from states to counties, and mortality-count allocation and socioeconomic modification of smoke–mortality associations. The observation period is 2009–2020. Supplementary Methods 1–7 define the inputs, allocation and inference; Supplementary Notes 1–6 connect main Figs. 1–4 to the complete evidence. These are followed by 22 supplementary tables, seven supplementary figures and independently numbered references. Supplementary Data 1–3 contain larger record-level tables. The five mortality categories overlap and are area-level outcomes, not five independent sets of patients.

## Supplementary Methods 1 Study units and mortality data

The health panel comprises 256 counties in Arizona, California, Colorado, Idaho, Oregon and Washington, with 15, 58, 64, 44, 36 and 39 counties, respectively. Each outcome has 12 years and 3,072 county–years, giving 15,360 county–year–cause records across five outcomes. State–year–cause groups impose the total-count constraints, with 360 groups. Exposure descriptions use unique county–years rather than weighting by repeated cause-specific rows. County FIPS and year identify geographical–temporal units, outcome IDs distinguish causes, and the archived row_id preserves alignment to columns of the saved allocation arrays. Population offsets use the corresponding annual population, not the ACS baseline population.

Supplementary Table 1 lists the five outcomes and ICD-10 ranges. COPD is nested within chronic lower respiratory diseases, which are nested within respiratory-system diseases; ischaemic heart disease is nested within circulatory-system diseases. The original ranges are retained without subtracting constituent diagnoses. These counts cannot be summed into a non-overlapping death total, and concordant directions do not constitute five independent replications.

Mortality data originate from CDC WONDER underlying-cause-of-death records [2]. Archived state responses retain the D76 query criteria, query dates of 26 July 2026, and settings to display zero and suppressed values. Thirty county-level state–cause export tables agree by key with all 15,360 analysis records for public counts, suppression flags, population and ICD codes; five state export tables agree with the 360 analysis totals and populations. This establishes export-to-analysis identity but does not complete the county-level original responses, full execution logs or data-use permissions.

Public zeros remain zero; counts marked Suppressed undergo the procedure in Supplementary Methods 4; missing values are neither zeros nor suppressed counts. The primary allocation support of 1–9 is a condition of the frozen extraction protocol and implementation, not a retrospective certification of that extraction by current help pages. Supplementary Table 8 reports suppressed records, public zeros and state-total remainders by outcome. Allocation arrays are not included as freely redistributable public source data.

## Supplementary Methods 2 Exposure scale and geographical matching

Smoke exposure uses the archived wildfire PM2.5 product of Childs et al. and its existing administrative-area aggregations [1]. Annual concentration is the sum of daily concentrations divided by 365.25, not a smoke-day mean. The archived annual concentration fields already contain this conversion and are not divided again. Every health model retains the fixed smoke IQR of 0.678107947271523 μg/m³. In Supplementary Equation 1, c, t and d denote county, year and day; N is the corresponding annual population and R is the set of counties being aggregated.

{{EQ:1}}

The state analysis retains 49 observed jurisdictions, including DC, yielding 588 state–years. Alaska and Hawaii lack smoke values throughout and remain in the 51-jurisdiction missingness ledger; neither zeros nor interpolated values replace them. Annual state distributions give each jurisdiction equal weight, whereas annual regional means across the six states weight counties by population. County long-term means first average each county's 12 years equally, and subsequent county distributions give each county equal weight. P10–P90 denotes geographical distributional percentiles, not confidence intervals. Annual between-county Gini uses unique counties and equal county weights (Supplementary Equation 2, with K counties), unlike the population-weighted mean.

{{EQ:2}}

The main maps retain archived 2020 Census cartographic boundaries [5] and exact FIPS joins. The contiguous United States uses an Albers equal-area projection; Alaska and Hawaii appear in separate insets where applicable, with missing and non-study areas coded separately. County matching checks names, state membership, unique FIPS and coverage of all 256 counties, without fuzzy matching, interpolation or silent deletion. Matching current boundaries to historical codes does not verify all historical boundary changes. Supplementary Figs. 1–2 and Supplementary Tables 3–5 provide state–year distributions, within-state county distributions and annual regional statistics. Supplementary Data 2 supplies 72 state-to-county comparisons. Close agreement between archived state values and population-weighted county aggregates does not establish identical upstream weights or historical boundaries.

## Supplementary Methods 3 Socioeconomic context and the fire catalogue

County disadvantage is a fixed composite score for the 2006–2010 baseline, re-standardized across counties in the six states to mean zero and sample standard deviation one; higher values indicate greater disadvantage. This baseline overlaps the first two observation years and is not wholly pre-follow-up. The local NHGIS dictionary describes the original score as the mean of standardized indicators within each period, and downstream code confirms use of the 2006–2010 field. However, the complete component list, directions, weights and missing-data rules are not adequately archived. Traceability of the composite and its downstream standardization does not make its upstream construction fully reproducible. Fixed scales are retained across outcomes and sample omissions. Supplementary Table 2 defines the variables and source limitations.

State poverty context is not the county composite disadvantage index. Archived poverty proportions derive from ACS five-year data and the B17001 definition of persons below poverty divided by the population for whom poverty status is determined [3,4]. State values are existing county poverty proportions weighted by total county population, rather than aggregation by the poverty universe or directly downloaded official state poverty rates. The archived year=2006 denotes the 2006–2010 five-year period, not a single-year observation. Supplementary Data 1 lists the baseline poverty proxy and 2009–2020 mean smoke for the 49 jurisdictions with smoke observations. No regression line, significance test or confidence band is added to the state scatterplot.

Fire context is restricted to 81 records dated 2009–2020 in the existing archived Top100 catalogue, retaining its original ranks, identifiers and area fields rather than re-ranking the full source database. The documented source family includes Interagency Fire Perimeter History and WFIGS [11,12]; current metadata do not establish the archived extraction version, query date, ranking or independent-event deduplication. Existing intersecting-state lists define state assignments; an existing centroid state is used when such a list is absent. Cross-state records count once in each state, so the 81 records yield 89 state assignments. Alaska records are retained despite missing smoke observations.

Supplementary Table 7 summarizes assignments to 13 states, and Supplementary Data 3 supplies all 81 records. The six states' 55 assignments represent 53 distinct catalogue records, not 53 verified independent fires. Eight records span states. Matching normalized names and years flags 12 groups and 28 records as potentially duplicated; all remain because event identity has not been resolved. Area is archived GIS_ACRES in acres. Burned area is not recalculated, and assignment shares are not interpreted as smoke, mortality or burned-area contributions.

## Supplementary Methods 4 Finite-support allocation of suppressed counts

For state–year–cause group g, T is the state total, O the set of publicly observed county cells, H the suppressed set and h its size. Subtracting all public counts from T gives remainder R. A feasible primary allocation requires h≤R≤9h; groups with h=0 receive no newly allocated counts. All observed values, including zeros, remain unchanged, and each allocated dataset satisfies the state total exactly (Supplementary Equation 3).

{{EQ:3}}

Fixed empirical-Bayes (EB) intensities multiply annual county population by a historical county cause-specific rate shrunk towards the corresponding state–cause rate. Supplementary Equation 4 uses D and P for cumulative public county counts and their corresponding populations during 2006–2020, and r for the historical rate aggregated from annual state totals over that period. Primary weights do not exclude the target year, unlike the leave-year-out validation in Supplementary Methods 5. The prior equivalent population E0 equals three times the median state–cause county–year population. Weights do not use smoke, disadvantage or their interaction and remain fixed across the 30 allocated datasets. The justification for the prior constant is incompletely archived, and associated uncertainty is not fully propagated.

{{EQ:4}}

Conditional on the remainder and intensities, the finite-support distribution is proportional to the product of Poisson weights (Supplementary Equation 5). The total constraint makes county allocations within a group dependent. Dynamic programming recurses from the end and then samples sequentially from conditional probabilities. F(j,r) is the weight that suppressed counties j through h sum to r, with F(h+1,0)=1 and zero weight for infeasible states. Supplementary Equation 6 gives the recurrence and sampling probabilities for primary support 1–9. The engine rescales each numeric-domain recursion row by its maximum, and sampling bounds respect the number of remaining counties; the validation engine operates in the log domain. These equations describe saved algorithms, not a new sampling run.

{{EQ:5}}

{{EQ:6}}

Each outcome has 30 saved allocated datasets and an archived random seed (Supplementary Table 13). These datasets describe allocation uncertainty conditional on the specified intensities, support and state totals, rather than 30 independent samples or recovered true hidden deaths. Outcomes were generated separately without joint parent–child constraints; Supplementary Note 4 reports the corresponding diagnostics and implications for cross-outcome calculations.

## Supplementary Methods 5 Pseudo-suppression validation and historical supporting analyses

Validation masks publicly observed counts of 10–19, uses support 0–19 and retains 100 saved allocations per method, unlike the primary support of 1–9 and 30 allocations. Historical training data cover 2006–2020, excluding the entire target year from training. The present evaluation retains the same 298 groups and 2,128 cells for the five outcomes during 2009–2020. Filtering saved evaluation records does not retrain the methods; bootstrap intervals from the older evaluation scope are not reused. All methods share identical group and cell identifiers, not merely equal sample sizes.

The four methods are equal weights, population weights, fixed EB and hierarchical EB. The first two use equal and population-proportional intensities. Validation EB uses a Gamma rate prior with shape max(r0τ,10^−8) and rate τ; the county posterior adds public training deaths to shape and corresponding cumulative population to rate. Marginal-likelihood optimization constrains τ to 10^3–10^9. Fewer than three training counties or r0≤0 triggers a fallback to three times median cumulative training-county population, or 10^6 if training records are absent; optimization failure also uses three times the median. Fixed validation uses posterior means, whereas hierarchical validation draws Gamma county rates for each 0–19 sum-constrained allocation. Target-year exclusion and weight learning should not be treated as identical to the primary fixed-weight workflow. Supplementary Table 9 reports MAE, RMSE and CRPS; Supplementary Table 10 reports nominal 95% allocation-interval coverage, mean width and interval score, for the five-outcome pool and all five outcome strata. MAE and RMSE compare allocation means with known public counts; CRPS uses the full empirical predictive distribution. Interval score penalizes both wide intervals and observations outside them. Metrics give evaluation cells equal weight. Count-interval coverage does not establish calibration for genuinely suppressed counts, regression effects or interaction intervals.

Historical COPD hierarchical reconstruction retained three chains, each with 200 warm-up iterations and 30 retained draws thinned every 10 iterations, giving 90 allocations. Supplementary Table 11 compares this with the primary 30 fixed-weight allocations. This is single-outcome supporting evidence, not joint validation of five outcomes or a formal equivalence test. Supplementary Table 21 includes only additional COPD models with traceable identities and observation years wholly within 2009–2020. Their different samples, allocation schemes and covariates must not be conflated with the current common-sample models.

## Supplementary Methods 6 Mortality associations and statistical inference

Each outcome and allocated dataset uses a negative-binomial log-link model (Supplementary Equation 7). County effects η and year effects τ control corresponding time-invariant or shared factors, and log N is the population offset. S is smoke scaled by the fixed IQR, D is fixed county disadvantage and X contains model covariates. The fixed main effect of D is absorbed by county effects, but the S×D interaction remains. Age, log(1+population density), drought, temperature and other environmental fields retain their archived transformations; Supplementary Table 14 defines the model branches.

{{EQ:7}}

The frozen procedure first fitted a Poisson mean to mean completed counts, then calculated dispersion α using Supplementary Equation 8 and held it fixed across the negative-binomial fits. The numerator subtracts the mean completed response, not the fitted mean; clipping restricts α to 0.001–2. This describes the frozen engine rather than a new fit. Supplementary Table 13 gives reference-model diagnostics; CIRC and IHD reach the lower bound.

{{EQ:8}}

Each fit uses a county-clustered sandwich covariance [8] with the finite-sample multiplier in Supplementary Equation 9. G is the number of counties, n the number of county–year rows and K the retained design-matrix columns. This covariance allows within-county dependence but does not automatically account for spatial dependence across counties. Allocation indices are not clustering units.

{{EQ:9}}

Each log-scale contrast Q and its county-clustered variance U are pooled using conventional Rubin rules [7] (Supplementary Equation 10), before transforming estimates and interval endpoints to 100[exp(Q)−1]%. When r=0, the frozen implementation uses 10^12 degrees of freedom; a normal approximation applies at degrees of freedom of at least 10^8. This is not the Barnard–Rubin adjustment. Supplementary Equation 11 defines FMI and the Monte Carlo error of the mean; dividing the latter by the total standard error gives MC/SE in Supplementary Table 13. Small FMI does not incorporate uncertainty in fixed weights, dispersion or every upstream data choice.

{{EQ:10}}

{{EQ:11}}

The interaction contrast Q=βSD gives a ratio of rate ratios (RRR) for a 1 SD increase in disadvantage and an IQR increase in smoke. At disadvantage s, the conditional smoke contrast and its variance retain the smoke coefficient, interaction and their covariance (Supplementary Equation 12), before pooling across allocated datasets. Exponentiation gives a conditional RR, not a population-standardized average association [10]. A positive interaction can coexist with negative conditional associations at some or all disadvantage levels and does not alone imply additional deaths.

{{EQ:12}}

Although five outcomes are reported, block A retains the saved Holm-adjusted P values from the original family of seven reference interaction tests [9], without recalculation for five. Blocks B–E comprise explanatory or sensitivity contrasts with unadjusted P values. All 95% CIs are ordinary two-sided intervals, not Holm simultaneous intervals. Retaining the historical adjustment does not remove risks from post hoc selection of the reporting scope; the five-outcome scope is not characterized as preregistered. This is an area-level observational analysis without intervention randomization or blinding; no prospective sample-size calculation is archived.

## Supplementary Methods 7 Model branches and paired samples

All eight block-C models use the same 3,062 county–years, 256 counties and six states with all M3PL_joint fields available and eligible relaxed daytime LST coverage. M2P is an independent precipitation branch. M3 adds non-fire PM2.5 and ozone to M2 and does not itself include precipitation. M3PL_joint adds non-fire PM2.5, ozone, precipitation and LST. The comparison in main Fig. 4d is C/M2 versus C/M3PL_joint, not the 3,072-row block-A reference model. Across these two models, county–year keys, row_id, row order and corresponding vectors from all 30 saved allocated datasets match for each outcome (Supplementary Table 22). Model-specific dispersion and degrees of freedom may differ.

Block D retains 3,072 rows in full, 2,816 after omitting 2020, 2,376 after omitting CA, 2,178 after omitting both CA and 2020, and 3,014 after omitting only CA's 2020 records. Fixed exposure and disadvantage scales are retained. These targeted omissions do not establish a difference between estimates merely because one is statistically significant and another is not.

Daytime LST uses May–October MOD11A2.061 eight-day products [6], aggregated by county over area and time and expressed per 10 °C in models. Strict QA requires bits 0–1=0, 2–3=0 and 6–7=0; relaxed QA requires bits 0–1≤1 and 6–7≤1. Both branches require seasonal coverage≥0.70, monthly coverage≥0.50 and all six months. Missing QC=0 is restored only where paired LST pixels are valid. Verification covers the archived QC-corrected products and earlier limited pixel checks, not a new audit of all raw rasters. LST is not personal heat exposure.

In block E, both −L/+L versions of relaxed M2 have 3,072 rows, and both versions of relaxed M3 have 3,062 rows; each covers 256 counties and six states. Strict M2 has 1,946 rows and 214 counties; strict M3 has 1,936 rows and 213 counties. Both strict branches cover five states and exclude AZ. Within a base model and QA branch, −L/+L use identical keys; comparisons across QA branches also change sample composition. Cross-model covariance is unavailable, so no new difference CI or P value is computed, and overlapping intervals do not establish equivalence. Source Data supply complete formulas, diagnostics and full-precision values.

## Supplementary Note 1 Exposure distributions from states to counties

State-equal annual means, medians and percentiles (Supplementary Table 3) describe annual differences among observed jurisdictions, not national population-weighted concentration. Supplementary Fig. 1 separately shows county-population-weighted state–year concentrations in the six states. Within-state county long-term distributions (Supplementary Table 4; Supplementary Fig. 2) retain every county; regional annual population-weighted means, county medians and Gini (Supplementary Table 5) use distinct, explicit weights. Statistics with different weights cannot substitute for one another or support an untested monotonic trend.

Across 72 state–year comparisons, mean absolute difference is 0.000386 μg/m³, maximum absolute difference is 0.004614 μg/m³ and the ratio ranges from 0.998066 to 1.002166 (Supplementary Data 2). This bridges the descriptions in main Figs. 1–2 without resolving incompletely archived upstream aggregation details. Supplementary Table 6 reports exposure by fixed disadvantage quintile. The archived county-level Spearman correlation between long-term smoke and disadvantage is 0.0825603685, without a newly computed P value. A weak or non-monotonic gradient does not demonstrate the absence of a causal socioeconomic influence on exposure inequality.

## Supplementary Note 2 Interpretation of economic context and catalogue records

Supplementary Data 1 compares a state baseline poverty proxy with long-term smoke. It does not identify an individual poverty–exposure relationship or make state poverty interchangeable with county composite disadvantage. Supplementary Table 7 and Supplementary Data 3 establish the catalogue's geographical context, not a prespecified rule for selecting six states or evidence of national representativeness. Extrapolation of the health results is limited by current coverage and model specification; catalogue assignments do not attribute exposure or mortality to individual fires.

## Supplementary Note 3 Benefits and limitations of allocation validation

In the five-outcome pooled evaluation, fixed EB has MAE 1.971983, RMSE 2.441581, CRPS 1.391503 and 95% count-interval coverage 97.5564%. Hierarchical EB has lower MAE (1.960028), while fixed EB has lower CRPS (hierarchical EB, 1.400846); no method should be called best on every metric. Supplementary Tables 9–10 also report all equal-weight and population-weight metrics rather than selecting favourable comparisons.

The primary panel contains 3,328 suppressed records and 325 public zeros (Supplementary Table 8). Suppression fractions use 3,072 county–years per outcome; the map uses 60 year–cause records per county. Hidden-death fractions instead use state death totals as their denominator. These are different quantities. Satisfying state totals and finite support does not turn allocated values into truth, and this validation evaluates pseudo-suppression at higher public counts. Similar historical fixed and hierarchical COPD results (Supplementary Table 11) cannot replace calibration for genuinely suppressed counts or joint multi-outcome validation.

## Supplementary Note 4 Nested-outcome consistency

Allocation-specific exceedances for the three retained child–parent relationships number 9,127, 3,197 and 506, each out of 92,160 county–year-by-allocation comparisons. Distinct county–years with at least one exceedance number 857, 585 and 146; mean counts across the 30 datasets still exceed their parents in 353, 27 and 9 county–years (Supplementary Table 12; Supplementary Fig. 3). The 2,178, 2,155 and 2,381 county–years where both counts are public have no violations. Units may overlap across relationships, so counts cannot be added.

Matching allocation indices across separately generated outcomes are not joint posterior draws; index-wise diagnostics are therefore not joint posterior violation probabilities. Inconsistent mean counts cannot be remedied by reordering allocation indices. These arrays do not support joint burden, cause shares or formal cross-outcome covariance. The diagnostics neither prove that every single-outcome estimate is invalid nor establish that a future joint reconstruction would leave estimates unchanged. Saved counts were not truncated, reordered or repaired.

## Supplementary Note 5 Complete associations for five outcomes

Supplementary Tables 15–19 report 5/25/40/25/40 rows for blocks A/B/C/D/E, respectively, totalling 135 rows. The machine-readable source uses outcome_id, analysis_block, model_id and contrast_id as a joint unique key and retains coefficients, standard errors, degrees of freedom, ordinary CIs, raw P values, block-A Holm values, and sample and allocation identities. Printed rounding does not alter full-precision source values.

Supplementary Table 15 reports reference interactions. Supplementary Table 16 and Supplementary Fig. 4 retain all 25 conditional contrasts at −2, −1, 0, +1 and +2 SD. Fifteen intervals lie wholly below zero and ten cross zero; none lies wholly above zero. The evaluation levels are within the observed disadvantage range of −2.852336 to 3.417321 SD, but that alone does not establish adequate local exposure overlap. Thus, the interaction describes relative changes in conditional associations across disadvantage, not positive smoke–mortality associations at every disadvantage level.

Supplementary Table 17 and Supplementary Fig. 5 show the eight genuinely common-sample environmental models. Supplementary Table 18 and Supplementary Fig. 6 retain every targeted omission, including results inconsistent with simple robustness claims. For IHD, the interaction after omitting 2020 is −0.232824% (95% CI −1.154461 to 0.697407); after omitting both CA and 2020 it is −1.472617% (−4.333467 to 1.473786). Supplementary Table 19 and Supplementary Fig. 7 present complete strict and relaxed LST pairs without attributing cross-sample changes to one environmental variable. These results limit claims of a uniform direction or broad robustness, without formally testing differences between models.

## Supplementary Note 6 Design concentration and historical COPD evidence

Supplementary Table 20 decomposes the residual sum of squares of the interaction design column after projection on the other design variables, by geography and year. CA's 58 records in 2020 comprise 1.888% of the 3,072 rows and 39.417% of the design residual sum of squares. This measures concentration of design contrast, not negative-binomial information, mortality burden or a causal contribution from CA in 2020. It helps contextualize targeted-omission sensitivity without identifying its sole source.

Supplementary Table 21 retains traceable historical additional COPD models with different covariates, periods and samples. Their task definitions accompany the table, and all shorter windows fall within the current observation period. These models add single-outcome methodological context rather than extend conclusions to five outcomes or join the eight common-sample models in Supplementary Table 17. No historical interval or test is re-estimated.

## Supplementary Discussion

Exposure distributions and association modification answer different questions. State and county maps describe where exposure is higher; the interaction describes how a model-conditional smoke association varies with county disadvantage. A weak exposure gradient can coexist with a positive interaction, but this does not demonstrate that economic conditions cause health inequality or exclude their influence on exposure. Area-level analyses remain susceptible to residual confounding, measurement error and ecological inference limitations.

Constrained allocation uses public state totals and finite support without resolving cross-outcome coherence or all upstream uncertainty. Conventional Rubin intervals remain conditional on fixed weights, dispersion and the archived workflow, and county clustering does not cover cross-county dependence. Single-outcome associations and their sensitivities can therefore be reported under the stated definitions, whereas joint burden, attributable deaths and causal mechanisms lie outside the evidence. Joint reconstruction or spatial inference would require additional analyses not supplied by this Supplement.

Reproducibility is limited by upstream records. Identity between archived CDC exports and the analysis panel has been checked, but original county responses and complete logs remain incomplete. Components and processing of county disadvantage, exact extraction versions for some covariates, and the fire catalogue's extraction and deduplication chain also remain unresolved. Accompanying Source Data contain processed values underlying the reported figures and tables, not every raw input. Formal sharing still requires author confirmation of third-party permissions, ethical approval or exemption, persistent repository deposition and access arrangements; a local companion package is not a public deposit.

{{TABLES}}

{{FIGURES}}

## Supplementary Data descriptions

Supplementary Data 1 contains baseline poverty proxies and long-term smoke for 49 jurisdictions with observed smoke. Supplementary Data 2 contains 72 pairs of archived state values and population-weighted county aggregates across six states and 12 years. Supplementary Data 3 contains 81 archived fire records, retaining original ranks, area, state assignments and potential-duplicate flags. These UTF-8 CSVs preserve original fields and full values; the English data dictionary explains fields, units, missingness and sources. Blank values must not be interpreted as zero.

## Supplementary References

{{REFERENCES}}
