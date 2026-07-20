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
| ~~`01`–`02` website-snapshot pipeline~~ | Deleted 2026-07-06 — the fda.gov website-export fetch and its gvkey crosswalk were fully superseded by scripts 03–05. Recoverable from git history (last present at commit `eb1e838`) if letter-level metadata (subject lines, letter links) is ever needed; the export endpoint gotcha (`X-Requested-With: XMLHttpRequest` header required) is noted in `data/README.md`. | Ryan | 🗑 Deleted |
| `03_fetch_fda_compliance_actions.py` | Download the FULL warning-letter history (FY2009+, all product types) from the FDA Data Dashboard — API mode (free key) or manual-download mode — and flag device/drug/biologic letters using FDA's own Product Type field. See [`data/fda_compliance_actions_replication_instructions.md`](../data/fda_compliance_actions_replication_instructions.md). | Ryan | ✅ Working (manual mode tested; API mode pending key) |
| `04_link_compliance_actions_to_gvkey.py` | Link the full-history warning-letter recipients to Compustat `gvkey` (same conservative match as 02; letter counts by unique Case ID; unmatched worklist limited to medtech/pharma). See [`data/compliance_actions_gvkey_crosswalk_replication_instructions.md`](../data/compliance_actions_gvkey_crosswalk_replication_instructions.md). | Ryan | ✅ Working |
| `05_backfill_subsidiary_gvkey_links.py` | Recover subsidiary→parent gvkey links script 04 can't see: curated crosswalks from the Clinical Trial Disclosure project (with ownership windows), parent-prefix matching (review-flagged), and a fuzzy worklist for manual accept/reject. Produces the **authoritative** `compliance_actions_gvkey_crosswalk_full_<date>.csv`. See Section 5 of the crosswalk replication doc. | Ryan | ✅ Working (Tier B + fuzzy worklist await manual review) |
| `06_descriptive_table_warning_letters.py` | Descriptive table (Table 1): warning letters by year — total, device, drug, biologic, and letters/firms linked to a gvkey (window-respecting, inclusive of review-flagged matches). Writes CSV + Markdown to `output/tables/`. | Ryan | ✅ Working |
| `07_device_firm_market_cap.py` | Market cap of gvkey-linked device-letter firms (Table 2): pulls `comp.funda` from WRDS, measures `prcc_f × csho` at the last fiscal year-end before each letter, writes descriptives to `output/tables/`. The letter-level panel stays gitignored (Compustat-derived values). | Ryan | ✅ Working |
| `08_device_universe_marketcap_share.py` | Table 3: total market cap of the US medical-device universe (SIC 3841–3845, US-incorporated) and the treated sample's share of it (61.4% of value from 16.5% of firms on first run); treated firms outside the universe reported separately. | Ryan | ✅ Working |
| `09_device_sample_descriptives.py` | Builds and saves the analysis sub-dataset (`data/processed/device_letters_linked_<date>.csv`, gitignored — carries Compustat-derived pre-letter market cap and total assets) and produces the paper's Table 1 descriptives in Markdown, CSV, LaTeX, and compiled PDF (`output/tables/`). | Ryan | ✅ Working |
| `10_fetch_part806_corrections_removals.py` | **Part 806 (corrections & removals).** Downloads the openFDA `device/recall` (58,756 records, back to 2000) and `device/enforcement` (39,519, carries Class I/II/III severity) bulk exports, then links recalls to sample firms by **exact FEI match** (primary) and normalized name (fallback), respecting ownership windows. First run (2026-07-19): **17,448 linked recalls, 113 firms**, 74% of links via exact FEI. Raw is universe-wide; processed is sample-restricted. | Ryan | ✅ Working |
| `11_fetch_part803_adverse_events.py` | **Part 803 (MAUDE adverse events).** Stream-filters the openFDA `device/event` bulk archive (25.4M reports, 362 quarterly partitions, 18 GB) keeping only sample-firm records — bulk-stream rather than API because openFDA allows only 1,000 requests/day without a key. Two-tier name linking (A: exact, B: parent-prefix, flagged). `--resume` restarts an interrupted run; `--since YYYY` limits years; `--keep-text` retains MDR narratives. First full run (2026-07-19): **10,737,528 MDRs across 177 firms**, 1991–2026, 362/362 partitions, ~50 min, 555 MB gzipped. ⚠️ **44% of matched records are Tier B (parent-prefix)** — see the caveat in `data/README.md`. | Ryan | ✅ Working |
| `12_link_fda_firm_names_to_gvkey.py` | **Generalized FDA-name → gvkey matcher.** Links firm names from ANY FDA source (806 recalls, 803 MAUDE, warning letters) to Compustat **independently of the letter data** — which is what makes a no-letter control group possible at all (scripts 10's FEI bridge is conditioned on treatment). Conservative exact-normalized matching, **SIC-gated to device (3841–5) or pharma/bio (2833–6)**; rejections logged to an audit file. First run: **594 firms unified, 294 with no warning letter** (245 device SIC). | Ryan | ✅ Working |
| `13_fetch_device_classification.py` | **Device classification lookup.** Pulls openFDA `device/classification` (7,075 product codes) into a joinable lookup keyed on `product_code` — the same key carried by both 803 MAUDE and 806 recalls, giving consistent device categories across the timeline. Adds regulation number, implant/life-sustaining flags. ⚠️ Does NOT fix MAUDE's 42% 'Unknown' specialty (that is FDA's own answer); `device_class` already agreed 100%. | Ryan | ✅ Working |
| `14_build_gvkey_year_event_panel.py` | **THE analysis panel.** One row per gvkey × year × event_type unifying all three stages (`warning_letter`/`recall`/`adverse_event`). Gated on `comp.funda`: firm must be publicly traded that fiscal year (same test as Table 1). First run: **2,712 obs, 141 firms, 1991–2025**; 58 firms in all three sources. Replaces the three standalone linked datasets. ⚠️ Ownership-window gate is near-vacuous (2 of 630 real windows) — funda gate is what binds. | Ryan | ✅ Working |
| `15_fetch_8k_event_disclosures.py` | **8-K event disclosures (outcome).** EDGAR full-text search → SIC filter → classify on the filing **lead** (text after each Item heading, or exhibit top), never the body (~6,300 body FPs avoided on WL alone). Untitled letters split to their own flag (no treatment counterpart). Product-domain vocabulary (device/drug/biologic). Text cached outside OneDrive. First run: 356 panel-event filings. | Ryan | ✅ Working |
| `16_build_device_8k_dataset.py` | **Medical-device 8-K subset.** Two-signal inclusion rule: device-domain text at any SIC, OR text-silent at a device-SIC filer — because text-only drops 71 real device events (Stryker, Invacare, Merit) and SIC-only drops 17 device events at pharma-classified filers. `device_evidence` records which signal qualified each row. **222 filings, 92 filers.** | Ryan | ✅ Working |
| `17_fetch_10k_10q_device_disclosures.py` | **10-K/10-Q device disclosure panel (Bozanic-style).** For the 140 gvkey-linked device firms, fetches 10-K/10-Q filings (2005+), extracts **Risk Factors (Item 1A) + MD&A (Item 7/Item 2)** via a widest-span rule, and counts per-event **mentions vs SUBSTANTIVE** (occurrence-window scoring: actual-event marker present, no local modal hedge). First run: 6,547 filings, 117 firms, 0 failures. Section text cached outside OneDrive. | Ryan | ✅ Working |
