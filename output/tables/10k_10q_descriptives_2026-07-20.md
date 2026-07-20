# 10-K / 10-Q device disclosure panel (2026-07-20)

| Statistic | Value |
|:---|---:|
| Filings | 6,547 |
| Firms (gvkey) | 117 |
| 10-K | 1,660 |
| 10-Q | 4,887 |
| Filing-year range | 2005-2026 |
| With Risk Factors section | 4,861 (74%) |
| With MD&A section | 6,238 (95%) |

## Event discussion: mentions vs SUBSTANTIVE (boilerplate-filtered)

| Event | Filings w/ mention | Filings w/ substantive | Total mentions | Total substantive | Substantive share |
|:---|---:|---:|---:|---:|---:|
| warning_letter | 2,176 | 970 | 11,179 | 5,398 | 48% |
| recall | 3,514 | 1,538 | 28,918 | 5,573 | 19% |
| adverse_event | 2,034 | 559 | 11,761 | 1,557 | 13% |

## Substantive mentions by section

| Event | Risk Factors | MD&A |
|:---|---:|---:|
| warning_letter | 2,540 | 2,858 |
| recall | 3,060 | 2,513 |
| adverse_event | 1,012 | 545 |

*Reading:* Risk-Factor mentions are overwhelmingly hypothetical (the substantive share there is the boilerplate test); genuine event discussion concentrates in MD&A. A mention is SUBSTANTIVE when its sentence ties the firm to an actual occurrence (past-tense receipt/action verb, a definite reference such as "the warning letter", or a specific date), not merely a modal risk disclaimer.

> **Caveats.** (1) Only Risk Factors (Item 1A) and MD&A (Item 7 / Item 2) are parsed; Legal Proceedings (Item 3) also carries actual recall/letter disclosures and is not captured here. (2) Item 1A was required only for fiscal years ending on/after 2005-12-01, so Risk-Factor coverage is thin before 2006. (3) Section boundaries are located heuristically (widest-span between item headers); a filing with non-standard headers can yield an empty section, flagged by `has_risk_factors` / `has_mda`.