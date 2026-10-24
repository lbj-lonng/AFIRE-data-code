# AFIRE Supplement build and verification scripts

These are local assembly, rendering, copying and read-only verification scripts. They do **not** fit mortality models, regenerate suppressed-count allocations, rerun pseudo-masking, calculate new inferential intervals, or recompute Holm adjustment. Numerical identities and descriptive consistency are checked against saved values; this is not a self-contained unrestricted model-refitting release.

## Scope and rerun safety

The version root is the parent of this directory. `scope_config.yaml` is JSON-compatible YAML and freezes the 2009–2020 / five-outcome scope, old-to-new numbering, fixed exposure scale and original seven-test Holm family. `content_CN.md`, `content_EN.md`, `figure_captions.json`, `equations.py`, `references.json` and `table_assets.py` are the authored assembly inputs. The actual main text is the current author-edited Chinese clean DOCX in the frozen baseline version; only its Supplement references are synchronized.

The scripts write into this new version's `submission/` and `audit/` trees, never the old experimental inputs. Re-executing a builder replaces its own generated outputs in this version and invalidates earlier visual sign-off unless hashes still match. To start another version, create a separate directory and explicitly re-point **all** output constants first. Several audit helpers have an absolute `OUT` path and must not be assumed portable just because other scripts use `__file__`. Do not run any historical builder imported from another version. Do not edit source values merely to make a hash check pass.

## Local runtime and dependencies

The verified interpreter for this project is:

```powershell
$afirePython = 'C:\Users\86189\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$afireScripts = 'D:\postgraduate\wildfire\9.10\9.15\AFIRE_Supplement_integrated_20260916_230522\scripts'
$env:PYTHONPATH = @(
  $afireScripts,
  'C:\Users\86189\Documents\Codex\2026-09-10\ban\work\pydeps',
  'D:\postgraduate\wildfire\9.10\AFIRE_threepart_mainfig_redesign_20260912_173900\_work\deps',
  'D:\postgraduate\wildfire\9.10\9.15\AFIRE_manuscript_figures_integrated_20260915_170300\_work\mathdeps'
) -join ';'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

These process-scoped dependency paths are read-only reuse of existing libraries, not imports of an earlier manuscript builder. `environment.py` sets task-local temporary and matplotlib-cache directories under `audit/`; it does not install dependencies. Principal packages used here are NumPy, pandas, matplotlib, Pillow, python-docx, lxml, pypdf, PyMuPDF, pdf2image, latex2mathml and mathml2omml. Some standard-library-only metadata helpers need no scientific packages. Package versions captured by the numerical/figure audits describe the actual local run; this folder is not a newly pinned environment lock or a promise that the paths exist on another computer.

The original baseline directory and specified historical source archives remain external dependencies. `plot_supplement.py` reads frozen figure tables directly from that baseline; `table_assets.py` also authenticates baseline tables. Full scientific verification reads existing allocation arrays **in place**, including an archived member in memory, but does not export those restricted arrays into `submission/`. To redraw or read the delivered artifacts, use the supplied aggregate tables; do not claim they contain all original model inputs.

## Actual build order

The following stages describe the dependency order. On this completed version, first inspect existing manifests and rerun only the stage that needs refreshing. Do not regenerate the whole package merely to read it.

1. **Historical/source inventory (optional full provenance rerun).** `audit_history.py` inventories old manuscripts and extracts text for comparison. `audit_upstream_readonly.py` checks archived county/state CDC exports, weight identities and source snippets. `build_history_reports.py` depends on the inventory and produces migration/author-edit reports. These scripts need the original project tree and write internal audits only; the curated interpretation is not an automated rediscovery of scientific truth.
2. **Frozen numerical verification and scoped source copies.** Run `verify_frozen_data.py --copy` for the initial new-version copy, or omit `--copy` for verification without copying. The copy path refuses to overwrite a different existing file. It excludes restricted arrays and obsolete public-table numbering, checks exact source hashes, retained outcomes/years, conservation and saved model identities. It computes diagnostics from saved data, but never fits or samples.
3. **Supplementary figures.** `plot_supplement.py` writes seven PDF/SVG/600-dpi PNG figures, figure-source CSVs and automated QA using `figure_qa_helpers/`. The frozen mapping is old S6/S7/S5/S1/S2/S3/S4 → new 1/2/3/4/5/6/7. Inspect every actual full figure and panel at final and embedded size before recording approval. A plot rerun resets visual-review status; PDF metadata may also change file hashes without changing the scientific drawing.
4. **Bilingual Supplement.** `build_supplement.py` calls `table_assets.prepare_tables`, loads both authored texts, converts `equations.py` through `math_format.py` to native Office Math, inserts the seven figures, renumbers references by first use, writes 22 editable tables, 12 display-equation groups and Data 1–3, and exports companion Data descriptions. Read `audit/build_EN.json` / `build_CN.json` and the actual DOCX, not just the script. The three Data files are exact deterministic 49/72/81-row transformations with a candidate-duplicate flag added to Data 3.
5. **Metadata and bibliography.** `write_data_documentation.py` writes the Source Data, geographic and Data-file README documents, actual-field dictionary, verified BibTeX, FIPS serialization checks and exact Data-transformation checks. Run after Data 1–3 exist. It asserts that all existing frozen source CSV hashes remain unchanged.
6. **Main-text link synchronization, only when required.** If the author has edited the source since the last synchronization, run `audit_concurrent_author_edit.py` first to preserve and document the prior synchronized copy. Then run `sync_maintext_si_links.py`; it changes only literal SI links, preserving all other ZIP parts and original equation/drawing XML. It never rewrites the author's scientific wording, editorial questions or unchanged four main figures. A new external author edit requires review of the baseline identity expected by final verification; do not silently replace the expected hash.
7. **Render actual DOCX files.** `render_documents.py` calls the local isolated renderer and copies successful PDFs into `submission/`. Existing render directories are moved into timestamped `audit/render_history/` paths before a fresh render. Page images and logs are generated under `audit/render/<document_stem>/`. Optional arguments are DOCX basenames, for example `Supplementary_Information_EN.docx`; with no arguments every `submission/*.docx` is rendered.
8. **Inspect, repair, then verify.** Inspect **every** final page image, all formulas, continuation tables and figure/caption placement. Correct assembly/layout inputs as required and rebuild/re-render affected documents. `record_figure_review.py` requires `--confirm-current-render-inspected` and expected image hashes; use it only after actual inspection. `record_maintext_visual_review.py` is a one-version recorder of manually entered page notes: it has no confirmation CLI and records current hashes rather than independently verifying the image content. It must not be blindly rerun after rendering changes; fresh inspection and updated notes are necessary. A changed image requires fresh inspection; never copy an old pass onto a new artifact. Supplement page-level review records are also maintained in `audit/visual_review_*.csv` by the current review workflow.
9. **Final checks.** `verify_history_source_hashes.py` verifies original historical inputs and separately reports the documented user-side source edit. `verify_supplement.py` compares actual final DOCX/table/math content, references, bilingual values, PDF/render manifests, scope and source hashes. Any FAIL is unresolved even if files exist. PARTIAL author/source/repository limitations are intentionally distinct from a rendering PASS and must remain visible in the handoff.

The additional `verify_cell_and_scope.py` independently compares every saved Word table cell with its language-specific expected text, scans final text containers using the excluded outcome IDs/names from the original configuration, and rechecks manifested source copies and selected historical tables. It does not use a row-wide bag of numbers as proof of cell identity. Its explicit non-OCR and scientific-interpretation boundaries are recorded in `audit/independent_verification_summary.json`. `verify_supplement.py` separately checks all 12 actual native display-math groups, embedded PNG hashes, final PDF-to-render identity, and every final page's current image hash against the inspection record. The aggregated `visual_review.csv` distinguishes completed inspection from inherited author-manuscript limitations.

Example assembly commands, after source verification and figure review:

```powershell
& $afirePython -X utf8 "$afireScripts\build_supplement.py"
& $afirePython -X utf8 "$afireScripts\write_data_documentation.py"
& $afirePython -X utf8 "$afireScripts\render_documents.py" Supplementary_Information_EN.docx Supplementary_Information_CN.docx
# Inspect the newly rendered pages before recording visual approval.
& $afirePython -X utf8 "$afireScripts\verify_history_source_hashes.py"
& $afirePython -X utf8 "$afireScripts\verify_cell_and_scope.py"
& $afirePython -X utf8 "$afireScripts\verify_supplement.py"
```

These commands are not a substitute for the optional prior source/figure/main-text stages. Do not run a visual-confirmation command as an unattended batch step.

## Isolated portable LibreOffice rendering

On this Windows host the wrapper explicitly prepends the task-managed portable renderer at `C:/Users/86189/Documents/Codex/2026-09-10/ban/work/libreoffice_renderer/program` and bundled Poppler at `C:/Users/86189/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin`. It asserts that the intended `soffice.exe` exists. This is a documented local fallback, not a claim that the Windows Python runtime bundles LibreOffice.

`render_docx_local.py` performs headless conversion using a fresh per-run `-env:UserInstallation=...` profile and temporary conversion directory. The wrapper places temporaries under this version's audit tree and permits at most two parallel render jobs. It does not automate the user's Word/Office desktop, replace an open document, or reuse a normal personal LibreOffice profile. It is a rendering copy of the document skill's local workflow, not an independent semantic DOCX converter.

DOCX is the editable source; the PDF/page PNGs are rendered evidence. Rendering differences, including mathematical baselines and table page breaks, are resolved through actual page inspection. A successful LibreOffice return code alone is insufficient. The renderer records the input DOCX SHA-256; the final PDF is accepted only with its matching current input and complete page images. Archived render directories are retained for audit, not candidates for final delivery.

## Supporting modules and residual limits

- `math_format.py` converts LaTeX/MathML to native OMML and contains narrowly documented renderer corrections; `equations.py` preserves scientific expressions. Do not replace equations with images to hide a rendering issue.
- `figure_qa_helpers/` audits source configuration, panel alignment, PDF text and label collisions. Automated geometry checks supplement, not replace, visual inspection.
- `record_figure_review.py` checks the expected inspected-image hashes; `record_maintext_visual_review.py` associates manual review notes with the current image hashes. Neither is a generic validator or a substitute for fresh inspection of a future version.
- `references.json` / `Supplementary_References.bib` preserve independently verified source identities; `audit/reference_numbering.csv` resolves manuscript numbering. They do not authenticate unknown upstream download snapshots.
- `audit_metadata.py` writes the explicit 61-row numbering ledger, 24-claim evidence map and 24-term bilingual terminology ledger, verifying every linked source file/hash. It does not replace the larger historical migration inventory. `finalize_delivery_report.py` writes the final report/checklist only after the aggregate verifier has no FAIL/NOT_RUN and all 60 final pages have current inspection records; it retains substantive PARTIAL items.
- `audit/author_action_needed.md`, the Supplement's limitations, and data READMEs identify unresolved author decisions, upstream provenance and redistribution issues. No script can automatically grant those permissions or convert a local folder into a public repository.

中文提示：复现仅限冻结数据的绘图、排版、复制和核验，不重新拟合或插补。旧版本和原实验目录只读；新一轮修改必须另建目录并检查全部输出路径。自动检查通过不代替逐页目检，来源和授权的 PARTIAL 事项也不能改写为 PASS。
