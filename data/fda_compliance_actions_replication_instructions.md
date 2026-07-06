# FDA Compliance Actions (Full History) — Replication Instructions

**Dataset:** `fda_compliance_actions_<YYYY-MM-DD>` (one snapshot per download date)
**Produced by:** [`scripts/03_fetch_fda_compliance_actions.py`](../scripts/03_fetch_fda_compliance_actions.py)
**Maintainer:** Ryan Barthel · **First built:** 2026-07-06

This document explains, step by step, exactly where this dataset comes from and how
to recreate it from scratch. It is written so that someone who has *not* built it
before can reproduce it. Read it top to bottom before running anything.

---

## 1. What this dataset is — and why it exists

A table of **every FDA compliance action** — Warning Letters, Seizures, and
Injunctions — from **October 2008 to the present**, across **all FDA product
areas**: medical devices, drugs, biologics, food/cosmetics, tobacco, and
veterinary.

It exists to fix the big limitation of our first warning-letter dataset
(script 01): the fda.gov website export is hard-capped at the most recent
~1,000 letters, reaching back only to about 2021. This dataset comes from a
different FDA system — the **FDA Data Dashboard** — and contains the full
history: about **174,000 warning letters over 18 years**, including roughly
**4,900 letters to device, drug, and biologics firms**, versus the 84 device
letters in the script-01 snapshot.

It also widens the project's scope from medical devices alone to
**medtech + pharma + biologics**, matching the expanded research design.

Each row is one company–product-type record of one compliance action. (A single
letter can appear on more than one row — see Section 5.)

---

## 2. Where the data comes from

| | |
|---|---|
| **Human-facing page** | https://datadashboard.fda.gov/oii/cd/complianceactions.htm |
| **Programmatic API** | https://api-datadashboard.fda.gov/v1/compliance_actions |
| **Access** | Public. The API needs a **free** authorization key (see 3a). The dashboard's download button needs nothing. |
| **Format** | CSV (dashboard download) or JSON (API). |
| **Update cadence** | FDA refreshes the data **weekly**; only *final* actions are included. |

### How this differs from the fda.gov warning-letters page (script 01)

| | Website export (script 01) | Data Dashboard (this script) |
|---|---|---|
| Coverage | most recent ~1,000 letters (~2021+) | **full history, Oct 2008+** |
| Industry field | none — we inferred "device" from office/subject text | **FDA's own Product Type** (Devices, Drugs, Biologics, …) |
| Firm identifier | company name only | company name + **FEI number** (FDA establishment ID) |
| Letter detail | subject line, response/closeout letter, link to letter text | none of those |

The two datasets are **complements**: this one defines the event sample
(who got a letter, when, in which product area); the script-01 snapshot adds
subject lines and letter links for recent letters.

---

## 3. How to reproduce it

### 3a. Preferred route — the API (fully scriptable)

1. **One-time:** request a free API key. On the
   [dashboard page](https://datadashboard.fda.gov/oii/cd/complianceactions.htm),
   follow the **"OII Unified Logon"** link, register with your name, email, and
   organization ("Self" is fine), and request an authorization key for the Data
   Dashboard API. FDA emails you the key.
2. Set two environment variables — your registered email and the emailed key:
   ```bash
   export FDA_DASHBOARD_USER="you@example.com"
   export FDA_DASHBOARD_KEY="<the key FDA emailed you>"
   ```
   (On Windows PowerShell: `$env:FDA_DASHBOARD_USER = "..."` etc.
   **Never commit the key to the repo.**)
3. Run, from the repository root:
   ```bash
   python scripts/03_fetch_fda_compliance_actions.py
   ```
   The script pages through the API 5,000 rows at a time (the documented
   maximum) until it has everything — about 35 requests.

### 3b. Fallback route — manual download (no key needed)

1. Open https://datadashboard.fda.gov/oii/cd/complianceactions.htm in a browser.
2. Click **Download Dataset → Entire Dataset** (do *not* apply any filters
   first). A CSV of ~17 MB downloads.
3. Run, from the repository root:
   ```bash
   python scripts/03_fetch_fda_compliance_actions.py path/to/downloaded.csv
   ```

Both routes produce identical raw-file layouts; the script validates the
columns and refuses files that look truncated or filtered.

### 3c. What you should see

A run on **2026-07-06** (manual route) produced:

```
raw snapshot              : 174,368 rows
dropped tobacco rows      : 164,573  (9,795 remain in the processed file)
date range                : 2008-10-01 to 2026-07-02
warning letters           : 9,481
   - device               : 1,799
   - drug                 : 2,842
   - biologic             : 230
   - medtech+pharma total : 4,871
```

Your numbers will be a little larger on a later date — FDA adds letters weekly.

---

## 4. What the script produces

| File | Folder | Description |
|---|---|---|
| `fda_compliance_actions_<date>.csv` | `data/raw/` | The **untouched** download, exactly as FDA served it. Never edit by hand. |
| `fda_compliance_actions_<date>.csv` | `data/processed/` | The **cleaned, analysis-ready** table with parsed dates and product-type flags. |

Both are **tracked in the (private) repo** — public U.S. government data, safe
to share — so Armando gets the exact point-in-time snapshot without re-running
anything.

### Columns in the processed CSV

The first eight columns are exactly as FDA provides them; the rest are added by
the script.

| Column | Source | Meaning |
|---|---|---|
| `FEI Number` | FDA | FDA Establishment Identifier of the firm/facility |
| `Legal Name` | FDA | Recipient company, as FDA wrote it |
| `State` | FDA | Firm state (or `-` for foreign firms) |
| `Country/Area` | FDA | Firm country |
| `Product Type` | FDA | FDA product area: Devices, Drugs, Biologics, Food/Cosmetics, Tobacco, Veterinary |
| `Action Taken Date` | FDA | Date of the compliance action (text) |
| `Action Type` | FDA | Warning Letter, Seizure, or Injunction |
| `Case/Injunction ID` | FDA | Unique ID of the action — the letter-level identifier |
| `action_taken_date` | script | `Action Taken Date` parsed into a real date |
| `company_name_clean` | script | `Legal Name` with extra spaces removed |
| `is_warning_letter` | script | `True` for Warning Letters (the project's treatment event) |
| `is_device` | script | `True` if `Product Type` is Devices |
| `is_drug` | script | `True` if `Product Type` is Drugs |
| `is_biologic` | script | `True` if `Product Type` is Biologics |
| `is_medtech_pharma` | script | `True` if any of the three flags above is true — **the project's analysis universe** |

Unlike script 01, the industry flags here are **FDA's own classification**
(the Product Type field), not keyword rules we wrote — a cleaner, more
defensible sample definition.

---

## 5. ⚠️ Things to know before analyzing

1. **One letter can span multiple rows.** FDA links a compliance action to
   every establishment and product type involved, so a single letter
   (`Case/Injunction ID`) can appear several times. **Count letters by unique
   `Case/Injunction ID`**, never by row. (2026-07-06 snapshot: 4,871
   device/drug/biologic rows = 4,683 unique letters.)
2. **~95% of raw warning letters are tobacco-retailer letters** — corner
   stores and vape shops cited for selling to minors. They are **dropped from
   the processed file** (design decision, 2026-07-06); the raw snapshot keeps
   them, so the decision is reversible by editing one clearly marked block in
   the script.
3. **Coverage starts October 2008** (fiscal year 2009). Letters before that
   are not in the Data Dashboard; if the project ever needs them, that is a
   FOIA / commercial-aggregator question (see the script-01 replication doc).
4. **Only final actions appear**, and FDA notes foreign-firm problems often
   surface as import alerts rather than warning letters — a caveat for
   interpreting foreign coverage.
5. **No subject lines or letter links.** Join to the script-01 snapshot (on
   company name + date) when those are needed for recent letters, or scrape
   letter text separately later.

---

## 6. Reproducibility checklist

- [x] Data pulled from a public FDA source — API (keyed, free) or documented manual export.
- [x] Raw download saved untouched and date-stamped (`data/raw/...csv`).
- [x] Every transformation done in code (`scripts/03_fetch_fda_compliance_actions.py`), not by hand.
- [x] Industry definition = FDA's own Product Type field (no keyword judgment calls).
- [x] Truncated/malformed downloads rejected loudly (row-count floor; column validation).
- [x] Known caveats documented above (row vs. letter counts; tobacco share; 2008 start).
