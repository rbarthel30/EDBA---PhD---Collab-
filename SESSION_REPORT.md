# Session Report — 2026-07-19

**Sample expansion: FDA regulatory timeline + 8-K disclosure outcomes**

Ryan Barthel · branch `ryan/fda-event-panel-and-8k-disclosures`

---

## 1. What this session set out to do

Expand the sample beyond warning letters alone to the **full medical-device
regulatory timeline** — adverse event → correction/removal → warning letter —
and build the **disclosure-response outcome dataset** those events are supposed
to explain.

Starting point: 120 warning letters, 81 firms (Table 1).

---

## 2. What was built

| Script | Purpose | Result |
|---|---|---|
| `10_fetch_part806_corrections_removals.py` | Part 806 corrections & removals from openFDA | 17,448 linked recalls, 113 firms |
| `11_fetch_part803_adverse_events.py` | Part 803 MAUDE adverse events (bulk-stream) | 10,737,528 MDRs, 177 firms, 1991–2026 |
| `12_link_fda_firm_names_to_gvkey.py` | Generalized FDA-name → Compustat matcher | 594 firms, **294 with no warning letter** |
| `13_fetch_device_classification.py` | Product-code lookup joining 803 ↔ 806 | 7,075 codes, 99.9% MAUDE coverage |
| `14_build_gvkey_year_event_panel.py` | **The analysis panel** | 2,712 obs, 141 firms, 1991–2025 |
| `15_fetch_8k_event_disclosures.py` | 8-K event disclosures via EDGAR | 356 panel-event filings |
| `16_build_device_8k_dataset.py` | Medical-device subset | **222 filings, 92 filers** |

### The panel (`gvkey_year_event_panel_2026-07-19.csv`)

One row per **gvkey × year × event_type**, gated on `comp.funda` (firm publicly
traded that fiscal year — the same test Table 1 applies).

| Event type | Obs | Firms | Events |
|---|---:|---:|---:|
| warning_letter | 98 | 71 | 106 |
| recall | 768 | 83 | 9,811 |
| adverse_event | 1,846 | 136 | 7,351,130 |

**58 firms appear in all three sources.** Co-occurrence within a firm-year:
adverse event only 58.1%, recall + adverse event 37.2%, all three 3.1%.

The funda gate dropped 41.6% of pre-gate rows (4,646 → 2,712); most of the loss
is firm-years with no Compustat record at all, not firms present-but-untraded.

### The outcome dataset (`8k_device_event_disclosures_2026-07-19.csv`)

| Event type | Filings | Filers | Via device text | Via SIC fallback |
|---|---:|---:|---:|---:|
| warning_letter | 151 | 64 | 99 | 52 |
| recall | 72 | 42 | 49 | 23 |
| adverse_event | 7 | 6 | 7 | 0 |

**124 of 222 are exhibits/press releases vs 98 8-K forms** — the press release is
the majority disclosure channel, which matters directly for the H2 framing tests.

---

## 3. Key methodological decisions

**Lead-based 8-K classification, never body text.** FDA-related 8-Ks routinely
mention all three event types even when about exactly one. The reference filing
(Beta Bionics, 2026-01-29) opens "received a warning letter" and then cites
"Medical Device Reporting" and "Correction and Removals" in the same paragraph —
a body regex flags it as all three. Classification therefore runs on the *lead*:
text after each `Item X.XX` heading, or the top of the document for exhibits.
Cost of the alternative, measured: **~6,300 false positives on warning letters
alone**.

**Two-signal device filter.** Neither text nor SIC alone works. Text-only drops
71 real device events (Stryker, Invacare, Merit Medical, Animas) whose filings
never name a product class. SIC-only drops 17 device events at pharma-classified
filers (the Abbott/J&J pattern). Rule: device text at any SIC, **or** text-silent
at a device-SIC filer. `device_evidence` records which signal qualified each row.

**Bulk-stream MAUDE, not the API.** openFDA allows 1,000 requests/day without a
key; a per-firm pull needs 10,000+ requests (~10 days). Streaming the 18 GB /
362-partition archive and discarding non-sample records takes ~50 min.

**Untitled letters split out.** Different regulatory artefact, and **absent from
the treatment panel entirely** (script 03 pulls Warning Letters, Seizures,
Injunctions). Folding them into `flag_warning_letter` would have inflated counts
with disclosures that can never link to an event. Confirmed as almost pure
risk-factor boilerplate: **2,976 body mentions, 2 lead-flagged**.

**Sample expansion came from recalls/MAUDE, not letters.** Script 12 added
exactly **1** warning letter. Its value is the 294 firms with regulatory events
but no letter — the control group that was previously *structurally impossible*,
because scripts 10/11 linkage was conditioned on having received a letter.

---

## 4. Known limitations — read before using these data

**Ownership windows are near-vacuous.** Only **2 of 630** crosswalk name-gvkey
pairs carry a real window; the rest default to 1900–2099. Scripts 05/10/11/14 all
enforce them faithfully and they constrain almost nothing. The `comp.funda` gate
is what actually binds. To fix: pull `comp.names` (`year1`/`year2`) from WRDS.

**MAUDE Tier B is 44% of matched reports** (4.7M of 10.7M). Parent-prefix matches
(`MEDTRONIC PLC` vs `MINIMED INC`) skew toward large acquisitive firms — exactly
the H4 population. Include/exclude is a research-design decision, not cleaning.
Split out as `n_mdr_tier_a` / `n_mdr_tier_b`; report both ways.

**Part 806 public recalls are a lower bound.** The 806 reports firms file are not
public; the RES database is the subset FDA classified and posted. Also
`voluntary_mandated` has **no variation** in the linked sample (all "Voluntary:
Firm initiated") and cannot serve as a moderator.

**Adverse-event disclosure is near-zero — 7 filings in 25 years.** Substantive,
not a parsing artefact: a single MDR isn't a material event. If H1 depends on MDR
disclosure the honest finding is a null. Better used as a continuous
regulatory-pressure control than as a treatment with its own response.

**MDR counts are reporting counts, not injury counts.** Reporting propensity
responds to FDA attention, which is endogenous to receiving a letter. FDA's
Alternative Summary Reporting program (retired 2019) means pre-2019 counts
understate events and the 2019 break is mechanical.

**EDGAR full-text search indexes 2001+ only**; the modern 8-K item structure
dates from August 2004, so the usable disclosure series starts ~2004 while the
panel runs 1991–2025.

**~42% of MAUDE has 'Unknown' medical specialty** — and this is *not* fixable:
those product codes are 'Unknown' in FDA's own classification table too. Use
`device_report_product_code` (2,902 codes, 100% populated) as a high-dimensional
category instead.

**Panel letter count (106) ≠ Table 1 (120).** Both use a funda gate, but Table 1
tests the *prior* fiscal year-end within 18 months while the panel tests the
event's *own* fiscal year. Not identical; align if the two must reconcile.

---

## 5. Deferred / not done

- **Compustat Global.** 524 of 1,751 device warning letters (29.9%) go to non-US
  firms and only 4.0% are linked (vs 13.9% for US). Estimated +50 letters,
  +30–40 firms. Needs an interactive WRDS pull. Note earnings-call transcript
  coverage for non-US firms is thin, so this expands financial-statement
  outcomes more than text-based ones.
- **Facility-level design.** FEI is facility-level (mean 2.1 per firm, max 13),
  which would support within-firm identification — deferred, since disclosure
  outcomes are firm-level.
- **Manual review queues:** `fda_firm_unmatched_worklist`, `fda_firm_ambiguous_names`,
  `fda_firm_out_of_industry`, `part806_unlinked_device_firms`.

---

## 6. Storage and reproducibility

Project footprint: **762 MB → 175 MB**. Caches moved outside OneDrive to
`%LOCALAPPDATA%\edba_fda_cache\` (MAUDE stream 442 MB / 362 chunks; EDGAR text
1.2 GB / 7,944 docs) — pure derived data with no information value beyond
rebuild speed, so syncing it to university cloud was wasted quota.

**Deleted (regenerable):** `part803_adverse_events_*.csv.gz` (556 MB, rebuild via
script 11 `--resume`, ~1 min) and `part806_corrections_removals_*.csv` (32 MB,
script 10 `--use-cached`, seconds). Both are inputs to script 14 — regenerate
before rebuilding the panel.

**Kept deliberately:** raw FDA snapshots (116 MB). FDA updates these weekly, so a
future re-download is a *different* snapshot; deleting would forfeit exact
reproducibility.

**Never committed:** Compustat extracts (licensed, WRDS terms).

⚠️ **Cache staleness:** the MAUDE cache is tied to openFDA `export_date=2026-07-14`
(recorded in `part803_manifest_2026-07-19.json`). `--resume` will happily reuse
stale chunks. **Clear the cache before any refresh intended to be current.**

---

## 7. Process notes

Five bugs were introduced and caught during this session. Four produced
**plausible-looking output rather than errors**, which is the reason they are
recorded here rather than quietly fixed:

1. **Chunk-name collision** (script 11) — cache keyed by quarter, so partitions
   overwrote each other. Lost 93% of records; the summary looked entirely normal.
2. **Null in `product_problems`** (script 11) — killed 163 of 362 partitions. The
   run still exited 0. Failures clustered in specific quarters, so the loss was
   *non-random by year*.
3. **Regex word boundaries** (script 15) — a non-raw patch string turned 84 `\b`
   into literal backspace bytes. Patterns compiled fine and matched nothing.
4. **Exhibit lead extraction** (script 15) — EDGAR full-text search returns the
   *matching file*, usually Exhibit 99.1, not the 8-K form. 88% of candidates had
   no `Item` heading, so the fallback classified them on arbitrary mid-document
   text.
5. **Glob picked a `_SUPERSEDED` sibling** (script 16) — sorts after the real file.

Two guards now in the pipeline exist because of these and should be kept:
a **reconciliation line** (`N chunks in scope of M partitions`) that makes a short
run announce itself, and **validation against known-answer cases** rather than
checking only that code ran.

Also corrected during the session: an early claim that the 806 linkage was "74%
exact FEI, no name matching" — FEI carries no firm identity, it *propagates* a
name-based link; and an unchecked assertion that the repo was public (it is
private, which is what makes committing derived identifier tables acceptable).

---

## 8. Suggested next steps

1. **Link the outcome to the treatment** — join the 222 device 8-Ks to panel
   events on gvkey/CIK and event year. That intersection (est. ~40–70 matched
   warning letters) is the H1 estimation sample.
2. **Decide the Tier B question** before any MAUDE-based result.
3. **Clear the manual review queues** — cheapest remaining sample gain.
4. **Compustat Global**, if the international extension is wanted.
5. **CRSP returns** for H6 event studies — not yet pulled.
