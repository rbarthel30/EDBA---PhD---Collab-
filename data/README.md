# Data Inventory

> **Reminder:** `data/raw/` and `data/processed/` are gitignored **by default**. A short allow-list in `.gitignore` tracks the shareable project datasets (public FDA files; the small gvkey crosswalk). **This repo is private.** Never commit licensed extracts (CRSP, Compustat *master*, IBES, Audit Analytics) or FOIA'd FDA materials — not even here.

This file lists every data source the project draws on, how to get it, and how it is used. Update as new sources are added.

---

## FDA Sources

### 1. FDA Warning Letters
- **URL:** https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters
- **Coverage:** The online database currently lists **~3,500 warning letters** across all FDA centers. The reliable scriptable export returns only the **most recent ~1,000** (currently reaching back to ~2021). Older letters are **not** available through any stable bulk download; back-fill options (FOIA / FDAzilla / a maintained browser harness) are documented in the replication doc.
- **Access:** Public, but **not in openFDA** (which has no warning-letters dataset). We download the website's `…/warning-letters/datatables-data` Excel export directly. ⚠️ That endpoint requires the HTTP header `X-Requested-With: XMLHttpRequest`, or it silently returns an empty spreadsheet.
- **How we pull it:** [`scripts/01_fetch_fda_warning_letters.py`](../scripts/01_fetch_fda_warning_letters.py); full walkthrough in [`fda_warning_letters_replication_instructions.md`](fda_warning_letters_replication_instructions.md). The script also flags the medical-device subset (issuing office + subject keywords).
- **Key fields (as exported):** Posted Date, Letter Issue Date, Company Name, Issuing Office, Subject, Response Letter, Closeout Letter.
- **Use:** Primary treatment variable. Flag firm-quarters in which a medical device manufacturer receives a warning letter.

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

### 5. MAUDE (Adverse Events)
- **URL:** https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfMAUDE/search.CFM
- **openFDA endpoint:** https://api.fda.gov/device/event
- **Use:** Adverse-event frequency as a control variable or alternative regulatory-pressure signal.

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

### 14. Warning Letter → gvkey Crosswalk *(built)*
- Files: `data/processed/warning_letter_gvkey_crosswalk_<date>.csv` (matched) and `warning_letter_unmatched_<date>.csv` (for manual linking). Tracked in this private repo; the full Compustat master they derive from stays gitignored.
- Links FDA warning-letter company names to Compustat `gvkey` via WRDS, conservative exact-ish match. See [`warning_letter_gvkey_crosswalk_replication_instructions.md`](warning_letter_gvkey_crosswalk_replication_instructions.md).

---

## Acquisition Status

| Source | Owner | Status | Date |
|---|---|---|---|
| FDA Warning Letters (most-recent ~1,000 snapshot) | Ryan | ✅ Done — see [`fda_warning_letters_replication_instructions.md`](fda_warning_letters_replication_instructions.md) | 2026-06-08 |
| FDA 510(k) database | Ryan | TODO | — |
| MAUDE | TBD | TODO | — |
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
