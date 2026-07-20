# Medical-device 8-K event disclosures (2026-07-19)

| Statistic | Value |
|:---|---:|
| Device event disclosures (8-K filings) | 222 |
| Distinct filers (CIK) | 92 |
| File-date range | 2001-2026 |
| Identified by device text | 148 |
| Identified by SIC fallback | 74 |

## By event type

| Event type | Filings | Filers | Via text | Via SIC fallback |
|:---|---:|---:|---:|---:|
| warning_letter | 151 | 64 | 99 | 52 |
| adverse_event | 7 | 6 | 7 | 0 |
| recall | 72 | 42 | 49 | 23 |

## By document type

| Lead source | Filings |
|:---|---:|
| Exhibit / press release (top) | 124 |
| 8-K form (Item-anchored) | 98 |

## Filings per year

| Year | Filings |
|:---|---:|
| 2001 | 4 |
| 2002 | 3 |
| 2003 | 2 |
| 2004 | 10 |
| 2005 | 11 |
| 2006 | 11 |
| 2007 | 10 |
| 2008 | 6 |
| 2009 | 8 |
| 2010 | 16 |
| 2011 | 6 |
| 2012 | 15 |
| 2013 | 17 |
| 2014 | 24 |
| 2015 | 14 |
| 2016 | 9 |
| 2017 | 12 |
| 2018 | 7 |
| 2019 | 7 |
| 2020 | 4 |
| 2021 | 12 |
| 2022 | 1 |
| 2023 | 6 |
| 2024 | 2 |
| 2025 | 2 |
| 2026 | 3 |

*Inclusion rule:* a filing is medical-device if its text scores as device domain (any SIC), or its text is silent on product class ('unspecified'/'mixed') AND the filer is device-SIC 3841-3845. Drug and biologic filings are excluded regardless of SIC, as are text-silent filings at pharma/bio filers. `device_evidence` records which signal qualified each row.

> **Caveats.** (1) Classification uses the filing's LEAD - the text after each `Item X.XX` heading, or the top of the document for exhibits/press releases - never the full body; body matching would have produced ~6,300 false positives on warning letters alone. (2) EDGAR full-text search indexes 2001+ only, and the modern 8-K item structure dates from August 2004, so earlier disclosures are absent by construction. (3) Adverse-event (MDR) disclosures are genuinely rare - firms seldom file an 8-K about an individual Medical Device Report - so that count is small for substantive, not technical, reasons.