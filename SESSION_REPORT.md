# Session Reports

Most recent first. Each report is self-contained; the 2026-07-19 report below
still holds the standing data limitations (MAUDE Tier B, ownership windows,
Part 806 lower bound) and should be read alongside this one.

---

# Session Report — 2026-09-28

**Subsidiary → parent crosswalk fix; full pipeline rebuild into `combined_9_28_26`**

Ryan Barthel · branch `main`

---

## 1. What this session set out to do

Answer "how many unique warning letters does the combined dataset hold?" and
reconcile it with Armando's 234 (a snapshot of the FDA website). That comparison
showed the gvkey linkage was systematically missing the LARGEST device firms, so
the session became a crosswalk fix and a rebuild of everything downstream.

---

## 2. Findings that motivated the fix

- **The FDA website is not our source and only covers 2021+.** Our 2008+ letters
  come from the FDA Data Dashboard (source #1). The website lists 3,701 letters,
  all issued Jan 2021 onward (224 CDRH-issued device letters; ~255 from all
  device offices) vs 241 device letters in our pull over the same window.
  Letter pages are HTML, not PDFs. **Armando's 234 could not be reproduced**
  from any cut of the 2008+ file; it is most likely a 2021+ website count.
- **The website's MARCS-CMS number = the dashboard's `Case/Injunction ID`**
  (verified 10/10), so letter text from the website joins to our events exactly.
- **Subsidiary names never reached the parent.** Abbott had 9 device letters and
  0 linked (letters go to "Abbott Medical", "Abbott Diabetes Care"); Philips 9/0;
  Baxter, Cooper, Zimmer Biomet, Danaher, Merit, Haemonetics, Teleflex were
  missing from the panel altogether.
- **Letters to acquired firms pointed at dead gvkeys** (Abiomed 2023, Beckman
  Coulter 2024, ZOLL 2026, MiniMed, DePuy, Respironics…) and silently dropped;
  others were **false matches** (CAO Group → NCO Group, Cook → Cook International
  deleted 1985, Noah Medical → Noah Holdings).

---

## 3. What was built / changed

**Decision (Ryan):** a letter to a subsidiary or acquired firm counts as an
event for the LISTED PARENT — the parent's stock is what moves.

| Item | Change |
|---|---|
| `data/external/project_subsidiary_parent_overrides.csv` | NEW, hand-curated: one row per ownership era (gvkey, years, closing date, note). ~100 FDA names. `UNMAPPED` = private / non-US-listed owner, or a neutralized false match |
| Script 05 | Reads the override file first (highest trust, `project_override_windowed`) |
| Script 10 | A name/FEI maps to a LIST of eras; a recall links to the era containing its year. Previously any name with >1 gvkey was dropped as "ambiguous" — all recalls at acquired firms were lost |
| Script 12 | Keeps every era row per name (was one row per name); names resolved to no listed owner block direct matches; reads MAUDE from the cache; no longer reads the header-only `part803_unmatched_manufacturers` file |
| Script 14 | `resolve_gvkey_by_era`: MAUDE reports re-assigned to the owner of the manufacturer name in the report year (MiniMed → Medtronic, 437k reports). `iter_maude_cache` reads the parquet cache directly. Recalls without a `cfres_id` dropped (1 row). Window note computed, not hard-coded |
| Script 11 | `--from-cache` rebuilds the processed extract from the cache with no network call |
| Script 18 | Inputs re-pinned; blank-ID recall rule aligned with script 14; universe market-cap re-pulled; output renamed **`combined_9_28_26`** (the 9/17 files and meeting PDF are untouched) |
| Docs | `data/README.md` (#7b, #15, #16), `scripts/README.md`, crosswalk replication doc **Section 5a** (how the override file works, for Armando) |

**Closing-year rule.** Windows are in years, so the year a deal closes goes to
whoever owned the business for most of it. Two exceptions so that no WARNING
LETTER lands on the wrong firm: Synthes (letter Feb 2012, J&J closed Jun 2012)
and Zhejiang Biomet (letter 3 Jun 2015, merger closed 24 Jun 2015).

### Headline numbers (9/17 → 9/28)

| | 9/17 | 9/28 |
|---|---:|---:|
| Device warning letters linked to a gvkey | 192 | **206** (117 firms) |
| ... at firms in the 10-K/10-Q panel | 128 | 164 |
| ... merged to a reporting quarter | 96 | **147** (139 filings) |
| Event panel (script 14): firms / letters / recalls | 141 / 106 / 9,811 | 172 / 172 / 16,322 |
| MDRs in the event panel | 7.35M | 8.29M |
| 10-K/10-Q filings / firms | 6,547 / 117 | **8,048 / 142** |
| Substantive MD&A rate, letter in quarter vs not | 37.4% vs 9.2% | 36.8% vs 9.4% |
| Share of US-listed device market cap | 79.9% | **85.6%** |

Reconciliation of script 18 against the script-14 panel: **0 mismatches** for
all three event types. Letters 2021+: 25 letters at 22 US-listed firms (of 241).

---

## 4. Known limitations — read before using these data

- **MAUDE under-captures firms that entered through the overrides.** Script
  11's cache was filtered at download time to the JULY name list, so reports
  filed under e.g. "Baxter Healthcare Corporation" are absent. Adverse-event
  counts for Baxter, Cooper, Zimmer Biomet, Danaher etc. are lower bounds until
  MAUDE is re-streamed.
- **Closing-year misplacement of recalls/MDRs.** With year-level windows, 72
  recalls and ~7,200 MDRs fall on the wrong side of a closing date (largest:
  ~5,000 Beckman Jan–Jun 2011 MDRs credited to Danaher; ~1,000 ZOLL Jan–Apr
  2012 MDRs dropped). Date-level windows would fix this.
- **Device 8-Ks not rebuilt** (scripts 15/16): newly added firms' 8-Ks missing.
- **July unified crosswalk is irreproducible.** It was built while
  `part803_unmatched_manufacturers_2026-07-19.csv` still held MAUDE names; the
  committed copy is header-only. The rebuild has 540 names (July: 630); none of
  the lost Compustat-direct names carries a device warning letter — only the
  no-letter control group is affected.
- **Non-US-listed parents are `UNMAPPED`** (Olympus, Terumo, Getinge, Asahi
  Kasei/ZOLL, Fresenius Kabi) — consistent with the US-listing universe, but it
  drops their letters from capital-market tests.
- Standing limitations from 9/17 and 7/19 (letter data from Oct 2008, lagged
  indicators, non-device firms in the panel, Tier B) all still apply.

---

## 5. Storage and reproducibility — ⚠️ READ THIS

**The MAUDE cache was deleted at session end (Ryan's instruction):**
`%LOCALAPPDATA%\edba_fda_cache\part803_stream\` (442 MB, 362 chunks, openFDA
export 2026-07-14) and the 556 MB processed extract were sent to the **Windows
Recycle Bin** (recoverable until it is emptied). Consequences:

- **Scripts 14 and 18 will stop with an error** (cache chunk-count check) until
  the cache is restored or re-streamed.
- **Script 12 would run but SKIP MAUDE names**, producing a different unified
  crosswalk than the committed 2026-09-28 one — do not re-run it without the cache.
- Re-streaming (script 11, 2–5 h) pulls the CURRENT openFDA export, not
  2026-07-14; counts will differ. Once the Recycle Bin is emptied, the
  2026-07-14 snapshot is gone for good.

All committed outputs (`combined_9_28_26.csv`, the panel, crosswalks) were
produced before the deletion and are unaffected. To rebuild once MAUDE is back:
05 → 12 → 10 `--use-cached` → 14 `--refresh-funda` → 17 → 18. The EDGAR text
caches (10-K/10-Q sections, 8-K text) remain in `%LOCALAPPDATA%\edba_fda_cache\`.

---

## 6. Process notes

1. **Override file first drafted without pre-acquisition eras** (MiniMed,
   Mentor, Animas, DePuy, Cordis, Medivators) — their pre-deal MDRs were
   dropped rather than kept with the target. Caught by auditing which MAUDE
   reports moved; fixed. Medivators' acquisition date was also wrong (1996, not
   2001; matches its Compustat deletion date).
2. **Stale funda cache** — script 14 would have gated the new parent firms out;
   re-pulled with `--refresh-funda`.
3. **Unified crosswalk shrank unexpectedly** (630 → 537) — traced to the deleted
   MAUDE extract and the header-only worklist, not to the fix.
4. **Reconciliation assertion caught a latent inconsistency** — a recall with no
   `cfres_id` counted by script 18 but not script 14; visible only once Cordis
   recalls stopped being dropped as "ambiguous".
5. Cache-based MAUDE reading was verified **byte-identical** to the extract-based
   outputs before the extract was removed.

---

## 7. Suggested next steps

1. **Re-stream MAUDE** under the new crosswalk (restores under-captured firms;
   accept a newer export).
2. **Date-level ownership windows** (closing-date precision).
3. **Re-run scripts 15/16** for the newly added firms' 8-Ks.
4. **Match Armando's letter PDFs** to events by MARCS-CMS = Case ID; decide
   whether to source 2009–2020 letter text from FDA's archive.
5. Carried over from 9/17: lagged/cumulative event indicators, device-industry
   screen, text measures, CRSP returns.

---
---

# Session Report — 2026-09-17

**Combined filing x event dataset (`combined_9_17_26`) and 9/17 meeting materials**

Ryan Barthel · branch `main` · commits `8f5658e`, `c04e4d4`, `3ebda9f`

---

## 1. What this session set out to do

Join the treatment side (FDA product events) to the outcome side (10-K/10-Q
disclosure, event 8-Ks) in ONE dataset - step 1 of the 2026-07-19 next steps -
and produce descriptives and a project-state summary for the 9/17 meeting.

Starting point: the gvkey-year event panel (script 14), the device 8-K dataset
(script 16) and the 10-K/10-Q disclosure panel (script 17, built 2026-07-20,
after the last report) existed separately and had never been linked.

---

## 2. What was built

| Item | Result |
|---|---|
| `scripts/18_build_combined_filing_event_dataset.py` | Builds the dataset + descriptives (md and pdf) in one run |
| `data/combined_9_17_26.csv` | **6,547 filings x 69 columns**, 117 firms, periods ending 2004-2026 |
| `output/tables/descriptives_combined_9_17_26.md` | Six descriptive tables + caveats |
| `meetings/descriptives_combined_9_17_26.pdf` | Same tables, compiled with pdflatex |
| `meetings/9_17_26_summary.md` | Ryan's research-question statement (verbatim) + short narrative of the descriptives |
| `scripts/10_...py` fix | `--use-cached` now actually uses the cached snapshot (see Section 6) |

### Design (Ryan's decision, after a first version was rejected)

A first build used the EVENT panel as the baseline and attached only filings
whose MD&A mentioned the event. Ryan rejected it: with only event rows there is
nothing to compare against. It was deleted entirely (never committed).

The dataset as built:

- **Baseline = the full 10-K/10-Q panel.** One row per filing = one firm
  reporting quarter (a 10-K is the fiscal Q4). Every filing is kept, so
  disclosure in quarters WITH a product event can be compared to quarters
  WITHOUT one.
- **Events merged in as counts** at gvkey x reporting year x reporting quarter:
  `n_warning_letter`, `n_recall` (+ class I/II/III), `n_adverse_event`
  (+ Tier A/B), with 0/1 flags. 10-K rows also carry fiscal-YEAR counts
  (`fy_n_*`, `fy_event_*`).
- **Event 8-Ks merged in the same way** (`n_8k_*`, unique accessions).

### Headline numbers

| | Warning letter | Recall | Adverse event |
|---|---:|---:|---:|
| Events at gvkey-linked firms | 192 | 17,448 | 10,737,528 |
| ... merged to a reporting quarter | 96 | 7,761 | 7,114,479 |
| Filings (quarters) with the event | 92 | 1,376 | 4,059 |
| Filings with a SUBSTANTIVE MD&A mention | 596 | 853 | 274 |
| Substantive rate: event in quarter vs not | 37.4% vs 9.2% | 21.1% vs 10.9% | 4.9% vs 3.0% |
| Substantive rate, 10-K level: event in fiscal year vs not | 24.4% vs 7.9% | 23.0% vs 12.4% | 7.7% vs 3.6% |
| Unique device 8-Ks (merged to a quarter) | 115 (62) | 62 (15) | 6 (5) |

Rates are raw, no controls.

---

## 3. Key methodological decisions

**Reporting quarter by period WINDOW, not calendar quarter.** Each event (and
8-K) is assigned to the filing whose reporting period contains its date
(`period_start < d <= period_end`). Reporting quarters are firm-specific:
Medtronic's end in Jan/Apr/Jul/Oct, and 52/53-week filers end a few days off a
month end (J&J: 2006-10-01). A calendar-quarter key was non-unique for **150
filings** and attached events to periods that had ended before them. The window
rule also guarantees ordering - every merged event precedes the filing it is
attached to (asserted at run time).

**32 bad EDGAR period dates imputed.** `reportDate` equals the filing date
(lag 0-5 days; the fastest genuine filer is 9 days). Period end is imputed from
the firm's fiscal-quarter cycle and flagged `period_end_imputed`.

**Event-level loaders reconciled to the script-14 panel.** The panel is yearly,
so quarter assignment needed event DATES, i.e. re-loading the sources. To
license that, script 18 re-aggregates its event-level rows to gvkey-year, applies
script 14's funda gate, and requires an EXACT match to the committed panel:
**0 mismatches across 98 / 768 / 1,846 cells** (106 letters, 9,811 recalls,
7,351,130 MDRs). Script 14's helpers are imported, not copied.

**MAUDE read from the script-11 cache, deliberately.** Re-running script 11
`--resume` today would pull a newer openFDA export and mix snapshots. The cache
(362 chunks, export 2026-07-14) is the snapshot the panel was built from; the
chunk count is asserted.

**comp.funda gate carried as a flag, not applied.** Applying it would recode
real event quarters as "no event" for SEC filers without Compustat market cap
(e.g. Biomet post-LBO) - treatment misclassification in exactly the comparison
the dataset exists for. `compustat_active_year` lets the gate be imposed later.
This is why 96 letters merge here vs 106 in the (gated, all-firm) panel - the
two are different samples, not a discrepancy.

**Fiscal-year counts assigned directly from event dates**, not by summing four
quarters, so a missing 10-Q cannot drop events from the year.

---

## 4. Known limitations — read before using these data

**Warning-letter data begins October 2008.** Before that, letters are
UNOBSERVED, not absent. `warning_letter_data_covered` (5,208 of 6,547 filings)
and `fy_warning_letter_data_covered` (1,270 of 1,660 10-Ks) mark usable rows.
**Any warning-letter event-vs-no-event test must restrict to covered rows.**
Recalls (2000+) and MAUDE (1991+) predate the panel and need no flag.

**An event is attached only to the period it is dated in.** Firms discuss a
warning letter for years: 596 filings substantively discuss one, but only 92
quarters contain one. "No-event" quarters are therefore contaminated by
continuing discussion of earlier events and are not yet a clean comparison
group. Lagged / cumulative event indicators are the natural next variable.

**Roughly a quarter to a third of events at panel firms do not merge** - nearly
all predate the firm's first filing in the panel (2005 start) or postdate its
last (acquired/delisted). Only 29 recalls fall in gaps between filings.

**Only 80 of 176 device 8-Ks belong to panel firms.** Script 16 drew on all
device filers, not only gvkey-linked firms. The 8-K side of the merged data is
thin (74 filings with an event 8-K in the quarter).

**Adverse-event reports arrive almost every quarter at large firms**, so
`event_adverse_event` has little within-firm variation there. Use the counts,
and Tier A / Tier B separately (the 2026-07-19 Tier B caveat still applies).

**Reporting year/quarter is a label** - calendar year and quarter of the period
end snapped to the nearest month end - not the firm's own fiscal-quarter number.

**The 117-firm filing panel includes firms that are not device companies** by
any ordinary reading (Walmart, Procter & Gamble, Rite Aid, Kimberly-Clark,
Illinois Tool Works appear). They enter through the FDA-name -> gvkey link, not
a device-industry screen. Not addressed this session; worth a sample decision.

**Still true from script 17:** Legal Proceedings (Item 3) is not parsed, so
event discussion located only there is missed.

---

## 5. Deferred / not done

- Lagged / cumulative event indicators (see Section 4).
- Outcome 1 text measures (sentiment, obfuscation, hedging/qualifiers) - the
  dataset currently carries mention and substantive-mention counts only.
- Earnings calls - not yet sourced.
- CRSP returns for outcomes 2 and 3 - still not pulled.
- A device-industry screen for the filing panel.
- Carried over from 2026-07-19 and untouched: Tier B decision, manual review
  queues, Compustat Global, `comp.names` ownership windows.

---

## 6. Storage and reproducibility

To rebuild `combined_9_17_26`:

1. `python scripts/10_fetch_part806_corrections_removals.py --use-cached` -
   regenerates the gitignored Part 806 file from the 2026-07-19 raw snapshot.
2. `python scripts/18_build_combined_filing_event_dataset.py`.

Requires the MAUDE cache at `%LOCALAPPDATA%\edba_fda_cache\part803_stream`
(362 chunks). **Do NOT run script 11 `--resume` first** - it would fetch a newer
export, and the panel reconciliation would (correctly) fail. Script 18 pins its
inputs by exact filename rather than globbing.

**Script 10 bug fixed.** `--use-cached` looked only for a raw snapshot dated
TODAY; on any later day it silently fell through to a fresh download - a
different FDA snapshot. The 2026-07-19 report's "regenerate via `--use-cached`,
seconds" instruction was therefore only true on the day it was written. It now
uses the most recent raw snapshot on disk and stamps outputs with that date.

---

## 7. Process notes

Problems introduced or found this session. As in July, most produced
plausible output rather than errors:

1. **Wrong baseline (design).** First build kept only event rows; rejected by
   Ryan and rebuilt. Cost: one full iteration.
2. **Warning-letter coverage.** The first with-vs-without table counted all
   2005-2008 filings as "no warning letter" when letters were unobserved. Found
   only while writing the note for the 10-K-level table; an already-delivered
   number changed (92 -> 91 event quarters; no-event 6,455 -> 5,117).
3. **Imputation threshold too wide.** A 15-day rule flagged a genuine 9-day
   filer (Abiomed). Caught by the key-uniqueness assertion, not by inspection.
4. **8-K document counts.** Counted every document of a flagged 8-K rather
   than flagged documents (recall 73 vs the correct 72). Caught by comparing to
   the 2026-07-19 report.
5. **Column-less empty MAUDE chunk** crashed the cache reader; now skipped and
   counted (1 of 362).

Guards now in script 18 that should be kept: exact reconciliation to the
script-14 panel, key uniqueness, event-precedes-filing, count conservation
through the merge, and the pinned MAUDE chunk count.

---

## 8. Suggested next steps

1. **Lagged / cumulative event indicators**, so the no-event group is clean.
2. **Decide the filing-panel sample** (device-industry screen).
3. **Text measures for outcome 1** on the cached MD&A / Risk Factor text.
4. **CRSP returns** for outcomes 2 and 3.
5. Carried over: Tier B decision, manual review queues.

---
---

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

*(Step 1 was done on 2026-09-17 - see the report above.)*

1. **Link the outcome to the treatment** — join the 222 device 8-Ks to panel
   events on gvkey/CIK and event year. That intersection (est. ~40–70 matched
   warning letters) is the H1 estimation sample.
2. **Decide the Tier B question** before any MAUDE-based result.
3. **Clear the manual review queues** — cheapest remaining sample gain.
4. **Compustat Global**, if the international extension is wanted.
5. **CRSP returns** for H6 event studies — not yet pulled.
