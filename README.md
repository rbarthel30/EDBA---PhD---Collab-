# FDA Comment Letters & Medical Device Disclosure

**A research collaboration between the University of Miami PhD Program in Accounting and the Executive DBA Program.**

---

## Research Question

> **What are the strategic disclosure and capital market impacts of FDA comment letters in the medical device industry?**

The project examines how publicly traded medical device firms respond — through voluntary disclosure, regulatory filings, and investor communications — to scrutiny from the U.S. Food and Drug Administration (FDA), and how capital markets price that scrutiny. It is the medical-device analog to the well-developed accounting literature on SEC comment letters (e.g., Cassell, Dreher & Myers 2013; Bozanic, Dietrich & Johnson 2017; Johnston & Petacchi 2017), extended to a setting where the regulator's letters target product safety, efficacy, and manufacturing quality rather than financial reporting.

## Author & Collaborator

| Role | Name | Affiliation | Contact |
|---|---|---|---|
| **Author** (EDBA paper) | **Armando Cuello** | UM Executive DBA — 20 yrs medical devices & big pharma, executive and biomedical engineer | a.cuello@umiami.edu |
| PhD Collaborator (econometric & data support) | Ryan Barthel | UM PhD in Business Administration, Accounting | rbarthel15@gmail.com |

**Premise.** This is **Armando's EDBA paper**. The collaboration is a mutual knowledge exchange: Armando brings deep industry expertise on FDA regulatory pathways, medical device manufacturing, and pharma/medtech operations; Ryan provides econometric, empirical-design, and data-infrastructure support, and in return gains exposure to the medtech/biotech industry.

## Repository Structure

```
EDBA_PhD-Collab/
├── README.md                  # This file
├── COLLABORATION.md           # Working agreement, roles, cadence
├── paper/                     # Manuscript drafts, outline, figures-for-paper
├── data/
│   ├── raw/                   # Untouched downloads from FDA, SEC, CRSP, etc. (gitignored)
│   ├── processed/             # Cleaned panels ready for analysis (gitignored)
│   ├── external/              # Reference tables, crosswalks, ticker mappings
│   └── README.md              # Data source inventory & access instructions
├── scripts/                   # Analysis code (Python / R / Stata)
│   └── README.md              # Script map: what each file produces
├── output/
│   ├── tables/                # Regression tables, summary stats
│   ├── figures/               # Charts, event-study plots
│   └── logs/                  # Stata/R logs for reproducibility
├── references/                # Methodology references, FDA documentation
├── literature/                # Key academic papers (PDFs gitignored; .bib tracked)
└── meetings/                  # Meeting notes, agendas, action items
```

## Empirical Setting in Brief

- **Sample.** Publicly traded U.S. medical device manufacturers (SIC 3841, 3842, 3843, 3844, 3845).
- **Treatment of interest.** Receipt of an FDA comment-style communication — primarily **Warning Letters**, **Untitled Letters**, and **FDA Form 483** observations issued following an establishment inspection — and the firm's subsequent disclosure response.
- **Outcomes.**
  - *Primary — Strategic disclosure:* whether, when, and how the firm chooses to disclose the letter and related information (8-K filings, MD&A risk-factor changes, IR communications, voluntary press releases, conference-call language, bundling with positive news).
  - *Secondary — Disclosure timing:* speed and channel of first public acknowledgment.
  - *Secondary — Capital market response:* short-window event-study abnormal returns, abnormal volume, bid–ask spread, analyst forecast revisions, institutional ownership changes — used to validate that strategic disclosure choices have economic consequences.

## Key Data Sources

See [`data/README.md`](data/README.md) for the full inventory and access notes. Headline sources:

- **FDA Warning Letters** — public database, [fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters)
- **FDA Form 483 observations** — obtainable via FOIA or commercial aggregators (FDAzilla)
- **FDA 510(k) and PMA databases** — device classification and approval history
- **MAUDE** — Manufacturer and User Facility Device Experience (adverse events)
- **SEC EDGAR** — 10-K, 10-Q, 8-K filings
- **CRSP** — daily stock returns
- **Compustat** — firm financials
- **I/B/E/S** — analyst forecasts
- **Audit Analytics** — *not* directly used for FDA letters, but valuable as a calibration benchmark from the SEC comment letter literature

## Workflow Conventions

- **Branching.** `main` is the protected default. Work on topic branches named `armando/<topic>` or `ryan/<topic>`. PRs reviewed by the other collaborator before merge.
- **Reproducibility.** Every script reads from `data/raw/` or `data/processed/`, writes only to `output/`. Random seeds set explicitly. Logs saved to `output/logs/`.
- **Data privacy.** Raw firm-level panels and any FOIA'd materials are gitignored. Never commit CRSP / Compustat / WRDS extracts — these are licensed.
- **Meeting cadence.** See [`COLLABORATION.md`](COLLABORATION.md).

## Quick Links
- [Data source inventory](data/README.md)
- [Literature](literature/README.md)
- [Meeting log](meetings/README.md)

## Status

🟡 **Project kickoff** — repository scaffolded May 2026. Currently in scoping / data-acquisition phase.

---

*University of Miami — Patti and Allan Herbert Business School*
