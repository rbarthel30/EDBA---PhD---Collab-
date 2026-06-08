# FDA Warning Letters — Replication Instructions

**Dataset:** `fda_warning_letters_<YYYY-MM-DD>` (one snapshot per download date)
**Produced by:** [`scripts/01_fetch_fda_warning_letters.py`](../scripts/01_fetch_fda_warning_letters.py)
**Maintainer:** Ryan Barthel · **First built:** 2026-06-08

This document explains, step by step, exactly where this dataset comes from and how
to recreate it from scratch. It is written so that someone who has *not* built it
before can reproduce it. Read it top to bottom before running anything.

---

## 1. What this dataset is

A table of **FDA Warning Letters** — public letters the FDA sends to companies it
believes are violating federal rules (e.g., manufacturing-quality or labeling
problems). For this project they are the central event: the moment a medical-device
firm comes under public FDA scrutiny.

Each row is one warning letter. The script adds flags identifying the **medical-device**
letters (the subset we care about), while keeping every other letter in the file too,
so the device definition can be revised later without re-downloading.

---

## 2. Where the data comes from

| | |
|---|---|
| **Human-facing page** | https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters |
| **Actual download endpoint** | the same URL with `/datatables-data` appended |
| **Access** | Public. No login, no API key, no license. |
| **Format returned** | An Excel (`.xlsx`) spreadsheet. |

The page shows the warning-letter table through a JavaScript widget (DataTables).
Behind that widget is a plain spreadsheet-export URL — that is what the script calls
directly, so we never have to automate a web browser.

### ⚠️ The one critical detail

The export URL **only returns data if the request includes the HTTP header
`X-Requested-With: XMLHttpRequest`.** Without that header it returns a spreadsheet
that is *valid but completely empty* — no error, just zero rows. This is a silent
trap that cost real debugging time; the script sets the header for you and, as a
safety net, **rejects and retries any download that comes back empty**. If you ever
re-implement this by hand, that header is the first thing to check.

---

## 3. How to reproduce it

### 3a. Prerequisites (one-time setup)

You need Python 3 with three packages:

```bash
pip install requests pandas openpyxl
```

- `requests` — downloads the file from FDA
- `pandas` — reads/cleans the spreadsheet
- `openpyxl` — lets pandas read `.xlsx` files

(On Ryan's machine these come with Anaconda and are already installed.)

### 3b. Run the script

From the repository root (the folder that contains `scripts/` and `data/`):

```bash
python scripts/01_fetch_fda_warning_letters.py
```

That's the whole process. The script prints a progress log and a summary, and
writes two files (next section). It needs no arguments and reads no input files —
it pulls a fresh copy straight from FDA each time.

### 3c. What you should see

A run on **2026-06-08** produced:

```
total letters in snapshot : 1,000
posted-date range         : 2021-03-30 to 2026-04-14
device letters (either)   : 84
   - flagged by office    : 74
   - flagged by subject   : 75
```

Your numbers will differ slightly if you run it on a later date, because FDA keeps
adding new letters (see the coverage note in Section 6).

---

## 4. What the script produces

| File | Folder | Description |
|---|---|---|
| `fda_warning_letters_<date>.xlsx` | `data/raw/` | The **untouched** download, exactly as FDA served it. Never edit this by hand. |
| `fda_warning_letters_<date>.csv` | `data/processed/` | The **cleaned, analysis-ready** table with parsed dates and device flags. |

> These FDA files are **tracked in the (private) repo** so Armando has the exact
> point-in-time snapshot without re-running anything. FDA Warning Letters are public
> U.S. government data, so they are safe to share. (`data/raw/`/`data/processed/` are
> ignored *by default*; these specific dataset families are allow-listed in
> `.gitignore`.) You can still always recreate them by re-running the script.

### Columns in the processed CSV

The first seven columns are exactly as FDA provides them; the rest are added by the script.

| Column | Source | Meaning |
|---|---|---|
| `Posted Date` | FDA | Date the letter was posted to the website (text, MM/DD/YYYY) |
| `Letter Issue Date` | FDA | Date FDA issued the letter (text, MM/DD/YYYY) |
| `Company Name` | FDA | Recipient company, as FDA wrote it |
| `Issuing Office` | FDA | FDA office that issued the letter (e.g., Center for Devices and Radiological Health) |
| `Subject` | FDA | Short description of the violation(s) |
| `Response Letter` | FDA | Whether a company response letter is posted |
| `Closeout Letter` | FDA | Whether a close-out letter is posted |
| `posted_date` | script | `Posted Date` parsed into a real date |
| `letter_issue_date` | script | `Letter Issue Date` parsed into a real date |
| `company_name_clean` | script | `Company Name` with extra spaces removed |
| `device_by_office` | script | `True` if the issuing office is a device-review office |
| `device_by_subject` | script | `True` if the subject names a device-specific program |
| `is_device_letter` | script | `True` if **either** of the two flags above is true — this is the medical-device subset |

---

## 5. How "medical device" letters are identified

We deliberately download **every** warning letter and then *tag* the device-relevant
ones, rather than filtering at download time. This keeps the raw data complete and
makes the device definition a transparent, editable rule.

A letter is flagged as a device letter (`is_device_letter = True`) if **either**:

1. **`device_by_office`** — the issuing office reviews medical devices. Matched offices
   include the Center for Devices and Radiological Health (CDRH), district "Office of
   Medical Device" operations, "OHT" product-evaluation offices, and named device
   product offices.
2. **`device_by_subject`** — the subject line names a device-specific regulatory
   program: Medical Device, QSR / Quality System Regulation (21 CFR 820), 510(k),
   PMA (Premarket Approval), IDE (Investigational Device Exemption), or Medical
   Device Reporting.

Using both rules matters: some genuine device letters are issued by **district offices
or CBER** rather than CDRH headquarters, and are only caught by the subject rule
(in the 2026-06-08 snapshot, 10 such letters would have been missed by an office-only
filter).

**These keyword lists are a research-design choice, not a fixed fact.** They live near
the top of the script, clearly marked as a decision point. Edit them to tighten or
loosen the device sample — for example, to decide whether COVID-era device letters or
Good Laboratory Practice (GLP) letters belong in the subset. Because the flags are
computed from the saved raw file, changing them requires **no re-download**.

---

## 6. ⚠️ Coverage limitation — read this

**This snapshot contains the most recent ~1,000 warning letters (all FDA centers),
which currently reach back to roughly 2021.** The FDA site lists about **3,500 letters
in total**, but it does **not** expose the older ~2,500 through any stable, scriptable
download:

- the bulk spreadsheet export is hard-capped at the most recent 1,000 letters;
- the "next page" buttons run only inside the website's JavaScript and cannot be
  driven reliably from a script; and
- the site offers **no date-range filter** on the export (only relative options like
  "last 90 days"), so we cannot request, say, "all letters from 2017."

For an initial analysis of recent medical-device letters, the most-recent-1,000
window is complete and fully reproducible. If the project later needs the **older**
letters (pre-2021), the realistic options are:

1. **FOIA request** to the FDA Division of Freedom of Information (the page itself
   points here for records not posted online).
2. **Commercial aggregator** such as FDAzilla, which sells historical warning-letter
   and Form 483 data.
3. **A maintained browser-automation harness** (e.g., Playwright) that clicks through
   the live table page by page. This is feasible but fragile, so it is intentionally
   *not* part of this reproducible script; treat it as a separate, Ryan-maintained tool
   if/when older coverage becomes necessary.

A second, minor note: the spreadsheet export tends to lag the live website by a few
weeks (on 2026-06-08 the export reached 2026-04-14 while the website showed letters
into June). Each snapshot is internally consistent and date-stamped, so this only
affects the very newest letters.

---

## 7. Reproducibility checklist

- [x] Data pulled live from a public FDA URL — no manual downloads, no licensed source.
- [x] Raw download saved untouched and date-stamped (`data/raw/...xlsx`).
- [x] Every transformation done in code (`scripts/01_fetch_fda_warning_letters.py`), not by hand.
- [x] Device definition encoded as editable, documented keyword rules.
- [x] Empty/failed downloads detected and retried, never silently saved.
- [x] Known coverage limitation documented above.
