# Scripts

Analysis code lives here. Every script reads from `data/raw/` or `data/processed/` and writes only to `data/processed/` or `output/`. Never edits its input.

## Naming Convention

Number scripts in the order they would run from scratch. Use a clear verb-first name.

```
01_scrape_warning_letters.py        # Pull FDA warning letters
02_parse_warning_letters.py         # Parse letter text → structured fields
03_build_firm_panel.py              # Join FDA + CRSP + Compustat → firm-quarter panel
04_event_study_returns.R            # Short-window event study around letters
05_disclosure_response.R            # Logit: P(8-K filed within X days | letter)
06_make_tables.R                    # Compile regression tables for paper
07_make_figures.R                   # Compile figures for paper
```

## Conventions

- **Languages.** Python for scraping, parsing, data wrangling. R or Stata for regressions. Whichever each collaborator is more fluent in.
- **Seeds.** Any randomized step sets `seed = 42` or another documented value.
- **Paths.** Use relative paths from repo root. Never hard-code `C:\Users\rxb1406\...`.
- **Logs.** Stata scripts open a log into `output/logs/`. R scripts use `sink()` to capture session info.
- **Headers.** Every script begins with:
  ```
  # =============================================================
  # Script: 03_build_firm_panel.py
  # Author: Ryan Barthel
  # Purpose: Construct firm-quarter panel from FDA, CRSP, Compustat.
  # Inputs:  data/raw/warning_letters_*.csv, data/raw/crsp_*.csv, data/raw/compustat_*.csv
  # Outputs: data/processed/firm_quarter_panel.parquet
  # =============================================================
  ```

## Script Map *(to be filled in as scripts are written)*

| Script | Purpose | Owner | Status |
|---|---|---|---|
| `01_fetch_fda_warning_letters.py` | Download FDA Warning Letters (most-recent ~1,000 snapshot) and flag the medical-device subset. See [`data/fda_warning_letters_replication_instructions.md`](../data/fda_warning_letters_replication_instructions.md). | Ryan | ✅ Working |
| `02_link_warning_letters_to_gvkey.py` | Link warning-letter company names to Compustat `gvkey` via WRDS (conservative exact-ish match). See [`data/warning_letter_gvkey_crosswalk_replication_instructions.md`](../data/warning_letter_gvkey_crosswalk_replication_instructions.md). | Ryan | ✅ Working |
| `03_fetch_fda_compliance_actions.py` | Download the FULL warning-letter history (FY2009+, all product types) from the FDA Data Dashboard — API mode (free key) or manual-download mode — and flag device/drug/biologic letters using FDA's own Product Type field. See [`data/fda_compliance_actions_replication_instructions.md`](../data/fda_compliance_actions_replication_instructions.md). | Ryan | ✅ Working (manual mode tested; API mode pending key) |
| `04_link_compliance_actions_to_gvkey.py` | Link the full-history warning-letter recipients to Compustat `gvkey` (same conservative match as 02; letter counts by unique Case ID; unmatched worklist limited to medtech/pharma). See [`data/compliance_actions_gvkey_crosswalk_replication_instructions.md`](../data/compliance_actions_gvkey_crosswalk_replication_instructions.md). | Ryan | ✅ Working |
| `05_backfill_subsidiary_gvkey_links.py` | Recover subsidiary→parent gvkey links script 04 can't see: curated crosswalks from the Clinical Trial Disclosure project (with ownership windows), parent-prefix matching (review-flagged), and a fuzzy worklist for manual accept/reject. Produces the **authoritative** `compliance_actions_gvkey_crosswalk_full_<date>.csv`. See Section 5 of the crosswalk replication doc. | Ryan | ✅ Working (Tier B + fuzzy worklist await manual review) |
| `06_descriptive_table_warning_letters.py` | Descriptive table (Table 1): warning letters by year — total, device, drug, biologic, and letters/firms linked to a gvkey (window-respecting, inclusive of review-flagged matches). Writes CSV + Markdown to `output/tables/`. | Ryan | ✅ Working |
