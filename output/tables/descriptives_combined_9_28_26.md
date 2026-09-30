# Descriptives - combined_9_28_26

Dataset: `data/combined_9_28_26.csv` - the full medical-device 10-K/10-Q panel (one row per filing) with FDA product events and event 8-Ks merged in by gvkey x reporting year x reporting quarter. Built by `scripts/18_build_combined_filing_event_dataset.py`.

## Overview

| Statistic | Value |
|:---|---:|
| Filings = firm reporting quarters (rows) | 8,048 |
| &nbsp;&nbsp;10-K | 2,026 |
| &nbsp;&nbsp;10-Q | 6,022 |
| Firms (gvkey) | 142 |
| Reporting periods ending | 2004-10-31 to 2026-08-15 |
| Filings with a parsed MD&A section | 7,603 |
| Filings with a warning letter in the quarter | 139 |
| Filings with a recall in the quarter | 1,774 |
| Filings with an adverse-event report in the quarter | 4,342 |
| Filings with no product event of any type in the quarter | 3,413 |
| Filings with an event 8-K in the quarter | 91 |

## Unique filings with a SUBSTANTIVE mention of each event in the MD&A

| Event substantively discussed in MD&A | 10-K filings | 10-Q filings | All filings | Share of all filings |
|:---|---:|---:|---:|---:|
| Warning letter | 153 | 591 | 744 | 9.2% |
| Recall (Part 806) | 319 | 757 | 1,076 | 13.4% |
| Adverse event (Part 803) | 125 | 183 | 308 | 3.8% |
| Any of the three (each filing once) | 430 | 1,123 | 1,553 | 19.3% |

*Counts are unique filings (accession numbers) across the FULL baseline panel, MD&A section only (Item 7 in a 10-K, Item 2 in a 10-Q). 'Substantive' = at least one MD&A occurrence tied to an actual event (past-tense receipt/action verb, definite reference, or specific date) and not hedged by a modal - script 17's definition. A filing can count under more than one event type.*

## Substantive MD&A disclosure: quarters WITH vs WITHOUT the event

| Event type | Filings: event in quarter | ... substantive MD&A | Rate | Filings: no event in quarter | ... substantive MD&A | Rate |
|:---|---:|---:|---:|---:|---:|---:|
| Warning letter * | 136 | 50 | 36.8% | 6,325 | 594 | 9.4% |
| Recall (Part 806) | 1,774 | 432 | 24.4% | 6,274 | 644 | 10.3% |
| Adverse event (Part 803) | 4,342 | 206 | 4.7% | 3,706 | 102 | 2.8% |

*Raw rates, no controls - descriptive only. 'Event in quarter' = at least one event of that type dated inside the filing's own reporting period. Discussion in a no-event quarter is mostly the continuing discussion of an EARLIER quarter's event, so the right-hand rate is not a clean counterfactual. * Warning-letter row uses only filings whose whole period falls on/after 2008-10-01, when FDA's letter data begins; earlier filings have letters UNOBSERVED, not absent, and are excluded rather than counted as no-event.*

## Substantive MD&A disclosure at the YEARLY (10-K) level: fiscal years WITH vs WITHOUT the event

| Event type | 10-Ks: event in fiscal year | ... substantive MD&A | Rate | 10-Ks: no event in fiscal year | ... substantive MD&A | Rate |
|:---|---:|---:|---:|---:|---:|---:|
| Warning letter * | 121 | 32 | 26.4% | 1,441 | 99 | 6.9% |
| Recall (Part 806) | 750 | 160 | 21.3% | 1,276 | 159 | 12.5% |
| Adverse event (Part 803) | 1,244 | 92 | 7.4% | 782 | 33 | 4.2% |

*10-K filings only. 'Event in fiscal year' = at least one event of that type dated anywhere inside the fiscal year the 10-K covers (previous 10-K's period end to this one's; all four quarters, not just Q4). Raw rates, no controls. * Warning-letter row uses only filings whose whole period falls on/after 2008-10-01, when FDA's letter data begins; earlier filings have letters UNOBSERVED, not absent, and are excluded rather than counted as no-event.*

## Event 8-Ks by event type

| 8-K event type | Documents (forms + exhibits) | Unique 8-Ks | ... at baseline-panel firms | ... merged to a reporting quarter | Filings (quarters) with such an 8-K |
|:---|---:|---:|---:|---:|---:|
| Warning letter | 151 | 115 | 73 | 68 | 66 |
| Recall (Part 806) | 72 | 62 | 28 | 27 | 26 |
| Adverse event (Part 803) | 7 | 6 | 5 | 5 | 5 |
| Any event (each 8-K once) | 222 | 176 | 100 | 94 | 91 |

*Source: the device 8-K dataset (script 16), classified on the filing lead. One 8-K can carry several documents (form + exhibits) and more than one event flag. Only 8-Ks filed by firms in the 10-K/10-Q baseline panel can merge; an 8-K is placed by its reported event date.*

## Product event dates (the events themselves - no filings involved)

| Event type - scope | Events | Distinct firm-dates | Firms | First event date | Last event date |
|:---|---:|---:|---:|---:|---:|
| Warning letter - all gvkey-linked firms | 206 | 200 | 117 | 2008-10-21 | 2026-01-29 |
| Warning letter - firms in the 10-K/10-Q panel | 164 | 159 | 91 | 2008-10-21 | 2026-01-29 |
| Warning letter - merged to a reporting quarter | 147 | 142 | 81 | 2008-10-21 | 2026-01-29 |
| Recall (Part 806) - all gvkey-linked firms | 19,077 | 6,546 | 118 | 2000-04-11 | 2026-06-30 |
| Recall (Part 806) - firms in the 10-K/10-Q panel | 14,834 | 5,001 | 95 | 2000-04-11 | 2026-06-30 |
| Recall (Part 806) - merged to a reporting quarter | 12,140 | 3,985 | 88 | 2004-08-17 | 2026-06-30 |
| Adverse event (Part 803) - all gvkey-linked firms | 10,571,163 | 239,588 | 214 | 1991-12-31 | 2026-06-30 |
| Adverse event (Part 803) - firms in the 10-K/10-Q panel | 10,140,038 | 197,362 | 133 | 1991-12-31 | 2026-06-30 |
| Adverse event (Part 803) - merged to a reporting quarter | 8,215,715 | 128,659 | 126 | 2004-09-03 | 2026-06-30 |

*Counted from the FDA source data. Event = one warning letter (unique Case ID, dated by action date), one recall record (dated when the firm initiated it), one adverse-event report (dated when FDA received it). 'Distinct firm-dates' counts each firm x calendar date once. Events not merged belong to firms outside the 10-K/10-Q panel, predate the firm's first filing in it (the panel starts in 2005; MAUDE in 1991), postdate its last, or fall in a gap between filings.*

## Industry coverage: panel share of the US publicly traded medical-device industry

| Statistic | Value |
|:---|---:|
| Firms in the 10-K/10-Q panel | 142 |
| &nbsp;&nbsp;in the US medical-device universe (counted in the share) | 44 |
| &nbsp;&nbsp;no current market cap (acquired, delisted or private since) | 63 |
| &nbsp;&nbsp;current market cap, but primary SIC outside 3841-3845 | 35 |
| &nbsp;&nbsp;device SIC, but not listed on a US exchange (OTC or foreign-listed) | 0 |
| &nbsp;&nbsp;memo: counted in the share but incorporated outside the US | 3 |
| US medical-device universe, firms | 172 |
| Panel firms as a share of universe firms | 25.6% |
| Share of US medical-device market capitalization | 85.6% |
| Market cap of panel firms in the universe ($M), mean | 25,600 |
| Market cap of panel firms in the universe ($M), median | 3,539 |
| Total assets of panel firms in the universe ($M), mean | 11,359 |
| Total assets of panel firms in the universe ($M), median | 2,646 |
| Fiscal year-ends at which market cap is measured | 2025-06-30 to 2026-06-30 |

*Share = current market capitalization of the panel firms that are in the US medical-device universe, divided by the universe total. Universe: Compustat firms listed on a US stock exchange (NYSE, NYSE American, NASDAQ or a US regional exchange; OTC-quoted firms excluded), whatever their country of incorporation, with primary SIC 3841-3845 and a computable market cap (fiscal year-end price x shares outstanding) at their latest fiscal year-end on or after 2025-06-30. Same as Table 1 of 2026-07-06 except that US LISTING replaces US incorporation, so foreign-incorporated US filers such as Medtronic plc count on both sides of the ratio. It is a CURRENT snapshot: panel firms acquired or delisted since they entered the sample contribute nothing, nor do panel firms whose primary SIC is outside the device codes, however large - so the share understates the panel's historical coverage. Source: Compustat (comp.company, comp.funda) via WRDS.*

## Caveats

1. Reporting year/quarter is the calendar year and quarter of the period end (snapped to the nearest month end) - a label for the firm's reporting period, not its own fiscal-quarter number. A 10-K row is the fiscal 4th quarter.
2. An event is attached ONLY to the quarter it is dated in. Firms keep discussing a warning letter for years, so lagged/cumulative event indicators are needed before reading the no-event rate as a counterfactual.
3. Adverse-event reports arrive almost every quarter at large firms, so event_adverse_event has little variation there; use the counts (n_adverse_event, and n_mdr_tier_a / n_mdr_tier_b separately - Tier B is parent-prefix name matching).
4. Events use script 14's ownership-window gate but NOT its comp.funda gate; compustat_active_year flags the firm-years that gate would keep.
5. Only Risk Factors and MD&A are parsed (script 17); event discussion located only in Legal Proceedings (Item 3) is missed.
