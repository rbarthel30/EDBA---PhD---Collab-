# 10-K / 10-Q device disclosure panel (2026-09-28)

| Statistic | Value |
|:---|---:|
| Filings | 8,048 |
| Firms (gvkey) | 142 |
| 10-K | 2,026 |
| 10-Q | 6,022 |
| Filing-year range | 2005-2026 |
| With Risk Factors section | 6,013 (75%) |
| With MD&A section | 7,603 (94%) |

## Event discussion: mentions vs SUBSTANTIVE (boilerplate-filtered)

Two denominators, kept separate on purpose. **Filing-level rate** = share of all filings that carry ANY substantive mention (the firm-quarter disclosure rate). **Substantive share of mentions** = of all occurrences of the term, the fraction that are real-event discussion rather than boilerplate.

| Event | Filings w/ mention | Filings w/ substantive | Filing-level rate | Total mentions | Total substantive | Substantive share of mentions |
|:---|---:|---:|---:|---:|---:|---:|
| warning_letter | 2,623 | 1,140 | 14% | 12,887 | 6,074 | 47% |
| recall | 4,317 | 1,908 | 24% | 35,592 | 7,089 | 20% |
| adverse_event | 2,424 | 645 | 8% | 13,602 | 1,739 | 13% |

*(Denominators: 8,048 filings; mention totals are occurrence counts across Risk Factors + MD&A.)*

## Substantive mentions by section

| Event | Risk Factors | MD&A |
|:---|---:|---:|
| warning_letter | 2,747 | 3,327 |
| recall | 3,691 | 3,398 |
| adverse_event | 1,129 | 610 |

*Reading:* Risk-Factor mentions are overwhelmingly hypothetical (the substantive share there is the boilerplate test); genuine event discussion concentrates in MD&A. A mention is SUBSTANTIVE when its sentence ties the firm to an actual occurrence (past-tense receipt/action verb, a definite reference such as "the warning letter", or a specific date), not merely a modal risk disclaimer.

> **Caveats.** (1) Only Risk Factors (Item 1A) and MD&A (Item 7 / Item 2) are parsed; Legal Proceedings (Item 3) also carries actual recall/letter disclosures and is not captured here. (2) Item 1A was required only for fiscal years ending on/after 2005-12-01, so Risk-Factor coverage is thin before 2006. (3) Section boundaries are located heuristically (widest-span between item headers); a filing with non-standard headers can yield an empty section, flagged by `has_risk_factors` / `has_mda`.