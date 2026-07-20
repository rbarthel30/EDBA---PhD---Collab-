# Data Inventory

This file lists every data source the project draws on, how to get it, and how it is used. Update as new sources are added.

---

## FDA Sources

### 1. FDA Compliance Actions — full warning-letter history *(primary event source)*
- **URL:** https://datadashboard.fda.gov/oii/cd/complianceactions.htm (FDA Data Dashboard)
- **Coverage:** **All Warning Letters, Seizures, and Injunctions from October 2008 (FY2009) to the present**, all FDA product areas. ~174,000 warning letters in the raw snapshot, of which ~4,900 rows (~4,700 unique letters) are to **device, drug, or biologics** firms. ⚠️ The **processed file drops the ~165k tobacco-retailer letters** (design decision 2026-07-06; the raw snapshot keeps them). Updated weekly; final actions only.
- **Access:** Public. Two routes: the documented **API** (https://api-datadashboard.fda.gov/v1/compliance_actions; free authorization key via the "OII Unified Logon" link on the dashboard page) or the dashboard's **Download Dataset → Entire Dataset** button.
- **How we pull it:** [`scripts/03_fetch_fda_compliance_actions.py`](../scripts/03_fetch_fda_compliance_actions.py); full walkthrough in [`fda_compliance_actions_replication_instructions.md`](fda_compliance_actions_replication_instructions.md). Industry flags come from **FDA's own Product Type field** (no keyword inference).
- **Key fields:** FEI Number, Legal Name, State, Country/Area, Product Type, Action Taken Date, Action Type, Case/Injunction ID.
- **Use:** Primary treatment variable — the event sample of FDA warning letters to medtech/pharma firms. ⚠️ Count letters by unique `Case/Injunction ID`, not rows (one letter can span establishments/product types).

### 1a. FDA Warning Letters — website snapshot *(retired 2026-07-06)*
- **URL:** https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters
- **Status:** Fully removed from the repo (datasets, docs, and scripts 01/02) — superseded by the Data Dashboard (source 1). Recoverable from git history (commit `eb1e838`) if ever needed. The website export (most recent ~1,000 letters only) is still the place to get **subject lines, response/closeout-letter indicators, and letter links**, which the dashboard lacks.
- **Gotcha (if ever re-implementing):** the `…/warning-letters/datatables-data` export endpoint requires the HTTP header `X-Requested-With: XMLHttpRequest`, or it silently returns an empty spreadsheet.

### 2. FDA Form 483 (Inspection Observations)
- **Coverage:** Issued at the close of an FDA inspection when investigators document objectionable conditions.
- **Access:** Not in a single public database. Options:
  - FOIA request to FDA
  - Commercial aggregators: **FDAzilla** (subscription)
  - Some companies disclose their own 483s
- **Use:** Earlier-stage regulatory signal than Warning Letters — 483s often precede warning letters. Useful for staggered-treatment designs.

### 3. FDA 510(k) Database
- **URL:** https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm
- **openFDA endpoint:** https://api.fda.gov/device/510k
- **Use:** Identify medical device manufacturers and their product portfolios; classify firms by device risk class.

### 4. FDA PMA (Premarket Approval) Database
- **URL:** https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm
- **openFDA endpoint:** https://api.fda.gov/device/pma
- **Use:** Class III high-risk devices. Firms in this subset may face different disclosure incentives.

### 5. MAUDE — Part 803 Medical Device Reports *(adverse events; built 2026-07-19)*
- **URL:** https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfMAUDE/search.CFM
- **openFDA endpoint:** https://api.fda.gov/device/event — **25.4M reports**, 1991–present, 362 quarterly bulk partitions (**18 GB zipped**).
- **How we pull it:** [`scripts/11_fetch_part803_adverse_events.py`](../scripts/11_fetch_part803_adverse_events.py). **Bulk-stream, not API** — openFDA allows only **1,000 requests/day without an authorization key**, so a per-firm API pull would take ~10 days. The script downloads each partition, keeps only sample-firm records, and discards the rest, so peak disk is ~100 MB rather than 18 GB.
- **⚠️ No universe-wide raw snapshot.** Unlike every other source here, we do not park the full archive in `data/raw/` (18 GB). Reproducibility comes from `part803_manifest_<date>.json`, which records the openFDA `export_date` and partition list.
- **⚠️ MAUDE has NO FEI number.** Firms are identified only by free-text `device.manufacturer_d_name`, so linking is name matching (Tier A exact / Tier B parent-prefix, flagged in `link_tier`). Exact-normalized matching alone hit **27.3%** of records in a 2023q1 prototype.
- **⚠️ Interpretation caveats.** MDR counts are *reporting* counts, not injury counts — reporting propensity responds to FDA attention, which is endogenous to receiving a letter. FDA's Alternative Summary Reporting program (retired 2019) let some firms file bundled reports, so pre-2019 counts understate events and the 2019 break is mechanical, not a real safety change.
- **Built 2026-07-19:** **10,737,528 MDRs across 177 firms**, `date_received` 1991-12-31 to 2026-06-30. 362/362 partitions, ~50 min, 555 MB gzipped (`part803_adverse_events_2026-07-19.csv.gz`). Streaming cache in `data/raw/_part803_stream_cache/` (442 MB, gitignored) — **clear it between substantively different runs**, since `--resume` skips on cached-chunk existence.
- **⚠️ Tier B is 44% of matched records** (4,738,314 of 10,737,528). That is far higher than the 27.7% seen in a single-quarter prototype, because MAUDE records divisions under operating names (`MEDTRONIC PLC` and `MINIMED INC` appear separately, as do `CARDIAC PACEMAKERS` and `DEPUY INC`). Including vs. excluding Tier B changes the sample by nearly half, and does so **non-randomly** — it disproportionately affects large acquisitive firms, exactly the firms H4 is about. Treat this as a research-design decision, not data cleaning, and report both ways.
- **Use:** First stage of the regulatory timeline (adverse event → correction/removal → warning letter); firm-level regulatory-pressure intensity.

### 5a. FDA Device Recalls — Part 806 Corrections & Removals *(built 2026-07-19)*
- **openFDA endpoints:** https://api.fda.gov/device/recall (58,756 records, back to 2000) and https://api.fda.gov/device/enforcement (39,519 records; carries recall **Class I/II/III**).
- **How we pull it:** [`scripts/10_fetch_part806_corrections_removals.py`](../scripts/10_fetch_part806_corrections_removals.py). Both bulk exports are single partitions (~360 MB total), so raw is kept **universe-wide**; the processed file is **restricted to sample firms**.
- **Linkage — the strongest in the project.** `device/recall` carries `firm_fei_number`, and so does the compliance-actions file, giving an **exact establishment-level join** with no name matching. First run: **17,448 linked recalls across 113 firms**, of which **12,923 (74%) linked via exact FEI** and 4,525 via normalized name (flagged in `link_source`). Ownership windows are enforced on the action-initiation year.
- **⚠️ These are not literally Part 806 filings.** The 806 reports firms send FDA are not public; what is public is the RES recall database — the subset FDA classified and posted. Treat the variable as *"publicly observable correction/removal activity,"* a **lower bound** on true 806 activity. Some records also arise under 21 CFR Part 7 rather than 806 proper.
- **⚠️ `voluntary_mandated` has no variation** in the linked sample — every non-missing value is "Voluntary: Firm initiated" (11,714 rows; 5,734 missing). It cannot serve as a treatment or moderator variable.
- **Key fields:** `firm_fei_number`, `event_date_initiated` (when the *firm* acted — the decision the paper is about), `root_cause_description`, `product_code`, `k_numbers`, `classification`, `recall_status`.
- **Coverage check:** 69 of the 81 Table-1 letter firms have ≥1 linked recall; 88 of 120 letters have a recall in the prior 3 years and 91 of 120 in the following 3 years.

### 6. FDA Establishment Registration & Device Listing
- **URL:** https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRL/rl.cfm
- **openFDA endpoint:** https://api.fda.gov/device/registrationlisting
- **Use:** Map firms to specific manufacturing facilities; useful when 483s are issued at the establishment level.

---

## SEC / Capital Markets Sources

### 7. SEC EDGAR
- **URL:** https://www.sec.gov/edgar
- **Access:** Public; use [`sec-edgar-downloader`](https://pypi.org/project/sec-edgar-downloader/) or the EDGAR REST API.
- **Filings of interest:** 10-K, 10-Q, 8-K (esp. Items 7.01, 8.01), DEF 14A, S-1.
- **Use:** Outcome variable on disclosure response. MD&A risk-factor changes (Section 1A). 8-K announcements following FDA letter.

### 8. CRSP
- **Access:** WRDS — Ryan has UM credentials.
- **Use:** Daily stock returns for short-window event study; daily volume and shares outstanding.

### 9. Compustat (Fundamentals Annual / Quarterly)
- **Access:** WRDS.
- **Use:** Firm financial controls — size, leverage, R&D, M/B, ROA.

### 10. I/B/E/S
- **Access:** WRDS.
- **Use:** Analyst forecast revisions and dispersion around FDA letter events.

### 11. Audit Analytics — SEC Comment Letters
- **Access:** WRDS (subscription).
- **Use:** *Not* directly used (the project is about FDA letters, not SEC letters). Useful as a **benchmark / calibration source** — the SEC comment letter literature (Bozanic et al., Cassell et al.) is the methodological template.

---

## Constructed / External Tables

### 12. SIC → Medical Device Classification
- File: `data/external/sic_medical_device.csv` *(to be constructed)*
- Mapping of SIC 3841–3845 to device sub-categories.

### 13. CIK ↔ Ticker ↔ FDA Establishment Crosswalk
- File: `data/external/firm_crosswalk.csv` *(to be constructed)*
- Built by matching firm names across EDGAR (CIK), CRSP (PERMNO), and FDA establishment registration database. Hand-validate edge cases.

### 14. Warning Letter → gvkey Crosswalk *(retired; replaced by #15)*
- The script-02 crosswalk built from the website snapshot (22 firms) was **removed from the repo (2026-07-06)** along with its replication doc and script — fully superseded by the full-history crosswalk in #15, which inherits its conservative matching philosophy.

### 16. Unified FDA Firm → gvkey Crosswalk *(built 2026-07-19 — use this for anything beyond letters)*
- **File:** `data/processed/fda_firm_gvkey_crosswalk_unified_<date>.csv` (script 12).
- **Why it exists.** The crosswalk in #15 is built from **warning-letter recipient names**, and script 10's FEI bridge only resolves at facilities that received a letter. Both routes are therefore **conditioned on treatment** — the 806/803 linkage could only ever find firms already in the letter sample. Script 12 matches FDA names straight to Compustat, independent of the letters, so a device firm with recalls or adverse events but **no letter** can enter the sample.
- **Result:** **594 firms**, of which **294 have no warning letter** (245 in SIC 3841–3845) — the potential control group.
- **Matching rules:** conservative exact-normalized match; a name hitting >1 gvkey is dropped, not resolved. **SIC-gated to device (3841–3845) or pharma/bio (2833–2836)** — the gate spans both because Abbott, J&J and Medtronic sit in pharma codes. Out-of-industry matches are rejected to `fda_firm_out_of_industry_<date>.csv` for audit (a spot-check caught `IMTEC Corporation` (dental implants) matching an unrelated `IMTEC INC` in SIC 5110).
- **⚠️ Historical names.** `comp.company` carries only each firm's **current** name, so a 2010 recall by "Guidant" will not match Compustat's "Boston Scientific". This under-matches older records; the hand-curated crosswalk in #15 patches it and **wins on conflict** when the two are merged.
- **⚠️ No ownership windows** on Compustat-direct rows (they are set 1900–2099). Joins that depend on real windows should prefer letter-crosswalk rows.

### 15. Compliance Actions → gvkey Crosswalk *(built — full history + subsidiary back-fill)*
- **Use this file:** `data/processed/compliance_actions_gvkey_crosswalk_full_<date>.csv` (script 05) — exact matches **plus** subsidiary links, with `match_source` provenance and **ownership-window columns** (`valid_from_year`/`valid_to_year`; joins must respect them). Intermediate files: `compliance_actions_gvkey_crosswalk_<date>.csv` (script 04, exact only), `compliance_actions_unmatched_remaining_<date>.csv`, and `compliance_actions_fuzzy_candidates_<date>.csv` (manual accept/reject worklist).
- Conservative exact matching (script 04) + tiered subsidiary recovery (script 05) using hand-curated crosswalks imported from Ryan's Clinical Trial Disclosure project (`data/external/ct_*.csv`). First run (2026-07-06): **241 unique public firms, 367 letters covered** (199 firms/266 letters from exact matching alone); 39 parent-prefix matches flagged for review; 4,123 names unmatched. See [`compliance_actions_gvkey_crosswalk_replication_instructions.md`](compliance_actions_gvkey_crosswalk_replication_instructions.md), Section 5.

---

## Acquisition Status

| Source | Owner | Status | Date |
|---|---|---|---|
| FDA Warning Letters (most-recent ~1,000 website snapshot) | Ryan | 🗑 Retired 2026-07-06 — superseded by the Data Dashboard pull; script 01 kept | 2026-06-08 |
| FDA Compliance Actions — full history FY2009+ (Data Dashboard) | Ryan | ✅ Done — see [`fda_compliance_actions_replication_instructions.md`](fda_compliance_actions_replication_instructions.md); API key request pending | 2026-07-06 |
| Compliance Actions → gvkey crosswalk (full history) | Ryan | ✅ Done — 241 public firms, 367 letters after subsidiary back-fill; Tier B review + 147-row fuzzy worklist remain | 2026-07-06 |
| FDA 510(k) database | Ryan | TODO | — |
| MAUDE / Part 803 adverse events | Ryan | ✅ Done — 10.7M MDRs, 177 firms, 1991–2026 | 2026-07-19 |
| Part 806 corrections & removals | Ryan | ✅ Done — 17,448 linked recalls, 113 firms | 2026-07-19 |
| Unified FDA firm → gvkey crosswalk | Ryan | ✅ Done — 594 firms, 294 with no letter | 2026-07-19 |
| Compustat **Global** (international letters) | Ryan | ⏳ TODO — needs interactive WRDS pull; 524 of 1,751 device letters (29.9%) go to non-US firms, only 4.0% currently linked | — |
| EDGAR (10-K, 8-K) | Ryan | TODO | — |
| CRSP / Compustat / IBES extract | Ryan | TODO | — |
| Warning Letter → gvkey crosswalk (Compustat) | Ryan | ✅ Done — 22 firms matched, conservative | 2026-06-08 |
| Firm crosswalk (full CIK/PERMNO) | Ryan + Armando | TODO | — |

---

## Data Hygiene Rules

1. **Raw is sacred.** Anything in `data/raw/` is *never* edited by hand. Scripts read from raw, write to processed.
2. **Document provenance.** Every file in `data/processed/` should be reproducible from a script that names its raw input(s).
3. **Date-stamp downloads.** When pulling from a public source, save as `<source>_<YYYY-MM-DD>.csv` so we can recreate the snapshot.
4. **Never commit licensed *master* extracts or PII.** The full CRSP / Compustat / IBES / Audit Analytics tables are never committed anywhere — collaborators regenerate them from WRDS. Small **derived** identifier tables (e.g., the warning-letter → `gvkey` crosswalk) may live in this repo **only while it is private**; if the repo is ever made public, they must be removed first.
