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
  # Author: Robert Barthelemy
  # Purpose: Construct firm-quarter panel from FDA, CRSP, Compustat.
  # Inputs:  data/raw/warning_letters_*.csv, data/raw/crsp_*.csv, data/raw/compustat_*.csv
  # Outputs: data/processed/firm_quarter_panel.parquet
  # =============================================================
  ```

## Script Map *(to be filled in as scripts are written)*

| Script | Purpose | Owner | Status |
|---|---|---|---|
| (none yet) | | | |
