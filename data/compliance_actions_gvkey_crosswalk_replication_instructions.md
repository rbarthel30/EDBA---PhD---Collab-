# Compliance Actions → Compustat gvkey Crosswalk — Replication Instructions

**Dataset:** `compliance_actions_gvkey_crosswalk_<YYYY-MM-DD>` (+ companion `compliance_actions_unmatched_<YYYY-MM-DD>`)
**Produced by:** [`scripts/04_link_compliance_actions_to_gvkey.py`](../scripts/04_link_compliance_actions_to_gvkey.py)
**Maintainer:** Ryan Barthel · **First built:** 2026-07-06

This is the full-history successor to the script-02 crosswalk. It links the
**~8,800 unique recipient names** on the full compliance-actions warning-letter
dataset (script 03; FY2009–present, all product types except tobacco, which
script 03 drops) to **Compustat firm identifiers (`gvkey`)**, so letters can
be joined to financial data, stock returns, and SEC filings.

Three standing rules, inherited from the original script-02 crosswalk:

- **WRDS access (one-time setup).** The script connects as
  `wrds.Connection(wrds_username="rxb1406")` (override with the
  `WRDS_USERNAME` environment variable). The password is read automatically
  from PostgreSQL's saved-credentials file — on Windows,
  `%APPDATA%\postgresql\pgpass.conf`, with a line like
  `wrds-pgdata.wharton.upenn.edu:9737:wrds:YOUR_USERNAME:YOUR_PASSWORD`.
  The first interactive `wrds.Connection()` call offers to create this file
  for you. No password ever appears in code or in the repo.
- **Conservative matching — we do not guess.** Company names are normalized
  (uppercase, punctuation stripped, corporate suffixes like Inc/Ltd/GmbH and
  noise words removed) and a link is accepted ONLY when a normalized name
  maps to exactly one gvkey. Names matching zero or several gvkeys stay
  unmatched. Precision is prioritized over recall: a low match rate is the
  correct, honest outcome, not a bug.
- **The full Compustat master (`data/raw/compustat_company_*.csv`) is never
  committed** — WRDS redistribution terms prohibit it, even in a private
  repo. Collaborators regenerate it by running the script. Only the small
  derived crosswalk (gvkeys + a few company names) is tracked here.

---

## 1. What changed vs. the script-02 crosswalk

| | Script 02 | Script 04 (this one) |
|---|---|---|
| Input letters | website snapshot, ~1,000 letters (2021+) | **full history, ~9,500 non-tobacco letters (Oct 2008+)** |
| Recipients matched | 979 unique names | **8,799 unique names** |
| Industry flags carried | device only (keyword-inferred) | **device / drug / biologic** (FDA's own Product Type) |
| Letter counting | rows | **unique `Case/Injunction ID`** (one letter can span rows) |
| Extra columns | — | first/last letter date; `product_types` list |
| Unmatched file | all unmatched recipients | **medtech/pharma recipients only** (see below) |

**Why the unmatched file is restricted:** ~95% of recipients are tobacco
retailers (corner stores, vape shops) with no Compustat record. The unmatched
file exists as a **manual-linking worklist**, so it keeps only the recipients
worth a human's time: those with at least one device, drug, or biologics
letter (~4,200 names). The *crosswalk* side is not restricted — a food or
tobacco firm that happens to match (e.g., Rite Aid) is kept.

---

## 2. How to reproduce

Prerequisite: script 03 has been run (its processed file is the input), and
WRDS credentials are set up (see the script-02 doc). Then, from the repo root:

```bash
python scripts/04_link_compliance_actions_to_gvkey.py
```

The script always uses the **most recent** `fda_compliance_actions_*.csv` in
`data/processed/` and re-pulls the Compustat master fresh from WRDS.

### What you should see

The first run, on **2026-07-06**, produced:

```
unique recipients               : 8,799
   - of which medtech/pharma    : 4,425
matched to gvkey (all types)    : 265
   - medtech/pharma firms       : 199
       * device                 : 117
       * drug                   : 77
       * biologic               : 9
   - flagged for review         : 27
medtech/pharma left unmatched   : 4,226
```

Those 199 matched medtech/pharma names account for **266 warning letters** —
versus 22 matched firms (11 device) in the script-02 crosswalk. A ~4.6% match
rate on the medtech/pharma names is expected and honest: most recipients are
private, small, or foreign manufacturing sites without a Compustat listing.

---

## 3. Output columns

Same as the script-02 crosswalk (`company_name_fda`, `normalized_name`,
`match_status`, `gvkey`, `company_name_compustat`, `n_gvkey_candidates`,
`review_suggested`, `n_letters`), plus:

| Column | Meaning |
|---|---|
| `first_letter_date` / `last_letter_date` | Date range of the recipient's warning letters |
| `any_device_letter` / `any_drug_letter` / `any_biologic_letter` | Product areas of the recipient's letters |
| `any_medtech_pharma` | Any of the three above — the analysis universe |
| `product_types` | All FDA product types on the recipient's letters, `;`-joined |

---

## 4. ⚠️ Known limitations / next steps

1. **`review_suggested = True` rows need a human glance** (31 in the first
   run). These matched on name but the corporate form differs (e.g., FDA says
   "Ltd", Compustat says "Inc"), or the name is generic ("Elevate") — the
   likeliest false positives.
2. **Subsidiaries are recovered by script 05** (Section 5 below) — exact
   matching cannot see that "Janssen Pharmaceutica N.V." is Johnson & Johnson.
3. **Same-name-different-firm risk.** The match is by name, not identifier;
   a private firm sharing a public firm's normalized name would match wrongly.
   The conservative rules make this rare, not impossible — spot-check before
   high-stakes use.

---

## 5. Subsidiary back-fill (script 05) — the file you should actually use

**Script:** [`scripts/05_backfill_subsidiary_gvkey_links.py`](../scripts/05_backfill_subsidiary_gvkey_links.py)
**Main output:** `compliance_actions_gvkey_crosswalk_full_<date>.csv` — the
**authoritative crosswalk** (script-04 exact matches **plus** subsidiary
links, with a `match_source` provenance column).

Run it after script 04 (no WRDS connection needed — it reuses script 04's
saved Compustat pull):

```bash
python scripts/05_backfill_subsidiary_gvkey_links.py
```

### The three tiers

| Tier | `match_source` values | Trust | Enters crosswalk? |
|---|---|---|---|
| A — curated | `ct_override_windowed`, `ct_override`, `ct_resolved`, `ct_dropped_device`, `ct_fuzzy` | high (hand-curated in Ryan's Clinical Trial Disclosure project) | yes, automatically |
| B — parent prefix | `parent_prefix` | medium — FDA name starts with a distinctive Compustat name (e.g., "ICU Medical Costa Rica Ltd.") | yes, but **every row is flagged `review_suggested=True`** |
| C — fuzzy | (none yet) | low | **no** — written to `compliance_actions_fuzzy_candidates_<date>.csv` for a human to mark accept/reject |

Tier A's inputs are three files copied into `data/external/` (prefix `ct_`)
from Ryan's Clinical Trial Disclosure project, where sponsor→gvkey links were
hand-curated: subsidiary overrides **with ownership windows**, an extended
sponsor crosswalk, and a device-sponsor list.

### Ownership windows — read this before joining

Some firms changed owners during our 2008–2026 sample (Genzyme was
independent until Sanofi bought it in 2011; Alexion joined AstraZeneca in
2021). The crosswalk therefore has `valid_from_year` / `valid_to_year`
columns, and such names appear on **multiple rows** (one per ownership era).
**Downstream joins must require
`valid_from_year <= year(letter date) <= valid_to_year`.** Rows for names
without ownership changes span 1900–2099, so the same join works everywhere.
Script 05 also **corrects** script-04 exact matches wherever the curated
windows say the name's owner changed (4 corrections in the first run).

`match_status = "resolved_unlisted_parent"` rows (26 in the first run) are
known subsidiaries of parents **not in Compustat North America** (e.g.,
Roche/Genentech). They carry no gvkey but are removed from the manual
worklist — they are explained, just not usable in capital-market tests.

### First-run results (2026-07-06)

```
exact (script 04)         : 195 names   (4 replaced by windowed corrections)
Tier A (curated)          :  41 names
Tier B (parent prefix)    :  39 names   (all review-flagged)
unique gvkeys             : 241
letters covered           : 367
resolved, unlisted parent :  26 names
still unmatched           : 4,123 names (147-row fuzzy worklist)
```

### The manual workflow that remains

1. Adjudicate the **39 Tier B rows** (`match_source = "parent_prefix"`):
   delete the wrong ones (generic prefixes like "All American …",
   "New England …") — ~10 minutes.
2. Work the **fuzzy worklist** (`compliance_actions_fuzzy_candidates_<date>.csv`,
   147 rows sorted by similarity): fill the `accept` column TRUE/FALSE.
   Beware word-order traps — "Pharmaceutical Innovations" is NOT
   "Innovation Pharmaceuticals".
3. Accepted decisions should be added to a project overrides file (same
   format as `data/external/ct_sponsor_overrides_supplemental.csv`) so they
   survive re-runs — talk to Ryan before doing this the first time.
