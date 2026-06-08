# Warning Letter → gvkey Crosswalk — Replication Instructions

**Dataset:** `warning_letter_gvkey_crosswalk_<YYYY-MM-DD>` (+ `warning_letter_unmatched_<YYYY-MM-DD>`)
**Produced by:** [`scripts/02_link_warning_letters_to_gvkey.py`](../scripts/02_link_warning_letters_to_gvkey.py)
**Maintainer:** Ryan Barthel · **First built:** 2026-06-08
**Depends on:** the FDA Warning Letters dataset — build that first
([`fda_warning_letters_replication_instructions.md`](fda_warning_letters_replication_instructions.md)).

This document explains how we link the company names on FDA Warning Letters to
**Compustat firm identifiers (`gvkey`)** so the letters can be joined to financial
and stock-market data. Read it top to bottom before running anything.

---

## 1. What this dataset is and why we need it

FDA writes warning letters to *companies*, identified only by a free-text name
("Medtronic, Inc."). To study capital-market effects we need each company's
**`gvkey`** — the permanent firm identifier used by Compustat (and bridgeable to
CRSP stock returns, SEC filings, etc.). This step builds that bridge:

> **FDA company name  →  Compustat `gvkey`**

The output is a **crosswalk**: one row per unique warning-letter recipient, with its
matched `gvkey` where we are confident, and a clear "unmatched" status otherwise.

---

## 2. Data sources

| Source | Access | Role |
|---|---|---|
| `data/processed/fda_warning_letters_<date>.csv` | produced by script 01 | the company names to match |
| **Compustat** `comp.company` (firm master) | **WRDS — licensed, UM login required** | the `gvkey` ↔ company-name reference |

> **Licensing — important.** Compustat is licensed data.
> - The **full Compustat master** (`data/raw/compustat_company_*.csv`, ~57k firms) is
>   **gitignored and must never be committed**, even to this private repo — WRDS
>   redistribution terms prohibit it. Regenerate it from WRDS.
> - The **small crosswalk** (`warning_letter_gvkey_crosswalk_*.csv`) and the
>   **unmatched list** ARE tracked, but only because **this repo was switched to
>   private**. They must not be moved to any public repo. They contain `gvkey`s
>   (proprietary S&P/Compustat identifiers) for ~20 firms.

---

## 3. Prerequisites

### 3a. Python packages

```bash
pip install pandas wrds
```

### 3b. WRDS access (one-time setup)

You need a **WRDS account with a Compustat subscription** (University of Miami
provides this). The first time you connect, the `wrds` package helps you save your
credentials to a local `pgpass` file so future runs are non-interactive:

```python
import wrds
db = wrds.Connection(wrds_username="YOUR_WRDS_USERNAME")
# It will prompt for your password once and offer to create the pgpass file — say yes.
db.close()
```

After that one-time step the script runs without prompting.

> **Tell the script your username:** set the `WRDS_USERNAME` environment variable,
> or edit the `WRDS_USERNAME` constant near the top of
> [`02_link_warning_letters_to_gvkey.py`](../scripts/02_link_warning_letters_to_gvkey.py).
> The password is never stored in the script — it comes from your local pgpass file.

> **No WRDS access (e.g., Armando)?** This step cannot be reproduced without a
> Compustat license — but you don't need to. The matched crosswalk and the
> unmatched list are committed to this **private** repo, so just pull them.

---

## 4. How to reproduce it

From the repository root, **after** building the FDA warning-letter file:

```bash
python scripts/02_link_warning_letters_to_gvkey.py
```

The script automatically finds the most recent
`data/processed/fda_warning_letters_*.csv`, pulls Compustat, matches, and writes
its output. A run on **2026-06-08** produced:

```
unique recipients         : 978
matched to gvkey          : 22
   - of which device firm  : 11
   - flagged for review    : 2
ambiguous (>1 gvkey)       : 0
unmatched (manual later)   : 956
```

**A low match rate is expected and correct.** Most warning-letter recipients are
private, very small, or foreign firms with no Compustat record. We deliberately do
**not** force matches; see Section 6.

---

## 5. What the script produces

| File | Folder | Description |
|---|---|---|
| `compustat_company_<date>.csv` | `data/raw/` | Untouched Compustat firm master pull (audit trail of the exact reference snapshot). |
| `warning_letter_gvkey_crosswalk_<date>.csv` | `data/processed/` | The **matched** firms, one row per recipient. |
| `warning_letter_unmatched_<date>.csv` | `data/processed/` | Recipients with **no confident match**, for manual linking later. |

### Columns in the crosswalk

| Column | Meaning |
|---|---|
| `company_name_fda` | Recipient name exactly as on the FDA letter |
| `normalized_name` | The cleaned key used for matching (uppercase, no punctuation/suffix) |
| `match_status` | `matched`, `unmatched`, or `ambiguous` |
| `gvkey` | Compustat firm identifier (blank if not matched) |
| `company_name_compustat` | The Compustat name the gvkey belongs to |
| `n_gvkey_candidates` | How many gvkeys the normalized name mapped to (1 = clean) |
| `review_suggested` | `True` if the match deserves a human glance (see §6) |
| `n_letters` | How many letters this recipient received in the snapshot |
| `any_device_letter` | `True` if any of its letters is a medical-device letter |

---

## 6. How matching works (and its deliberate conservatism)

The agreed design is **scope = all recipients, method = conservative exact-ish only**.

1. **Normalize** both the FDA name and every Compustat name (`conm` *and* legal name
   `conml`): uppercase, remove punctuation, and strip corporate-form suffixes
   (INC, LLC, LP, CORP, CO, LTD, GMBH, SA, PLC, …) and noise tokens (THE, GROUP,
   HOLDINGS, …).
2. **Match only on an exact normalized-name equality**, and **only when that name
   maps to exactly one `gvkey`.** If it maps to several (`ambiguous`) or none
   (`unmatched`), we do **not** assign a gvkey.

This favors **precision over recall**: we would rather leave a firm unmatched than
attach the wrong `gvkey`. The unmatched firms are exported separately so they can be
linked by hand later (or with a looser, human-reviewed method) without redoing the
confident matches.

### The `review_suggested` flag

Stripping suffixes can occasionally over-match a US-style entity to a similarly
named foreign one. The flag marks any match where the FDA name and the Compustat
name carry **different entity families** (US-style INC/CO/LLC vs foreign
LTD/PLC/GMBH/…). These are *not* dropped — they are surfaced for a quick human check.

In the 2026-06-08 run, two matches were flagged:

| FDA name | Matched Compustat name | Verdict |
|---|---|---|
| `Medtronic, Inc.` | `MEDTRONIC PLC` | **Correct** — Medtronic reincorporated in Ireland (PLC) in 2015. |
| `Tropic Trading Co.` | `TROPIC TRADING LTD` | **Likely false positive** — different entity types; confirm or drop by hand. |

Because there are only ~20 matches, it is practical to **eyeball the entire crosswalk**
each run; the flag just tells you where to look first.

---

## 7. Known limitations & sensible next steps

- **Recall is low by design.** Only firms whose name matches Compustat *exactly after
  normalization* are linked. Public firms written very differently from their
  Compustat name (subsidiaries, "d/b/a" names, post-merger renames) will sit in the
  unmatched file until linked by hand.
- **Point-in-time names.** We match against Compustat's *current* `conm`/`conml`. A
  firm that has since been renamed or acquired may match under its new name, not the
  name on an older letter. For event-study work, validate the match date against the
  letter date.
- **gvkey is the firm, not the security.** To get stock returns you still bridge
  `gvkey` → CRSP `permno` (via the CRSP/Compustat Merged linktable, `crsp.ccmxpf_lnkhist`).
  That is a separate, later step.
- **Manual back-fill.** The intended workflow is: keep these confident matches, then
  work through `warning_letter_unmatched_<date>.csv` by hand (or with fuzzy matching
  plus review) for the firms that matter to the analysis.

---

## 8. Reproducibility checklist

- [x] Compustat pull saved untouched and date-stamped (`data/raw/compustat_company_*.csv`).
- [x] Every transformation done in code, not by hand.
- [x] Matching rule is explicit, conservative, and precision-first (exact normalized, unique-gvkey only).
- [x] Unmatched recipients exported for transparent manual linking — nothing silently discarded.
- [x] Risky matches flagged (`review_suggested`), not hidden.
- [x] Full Compustat master kept out of git entirely (gitignored); crosswalk shared only via the private repo.
