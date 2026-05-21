# Collaboration Agreement

A working document for how Armando and Ryan run this project together. Living document — update as the working relationship evolves.

## Roles

| Domain | Owner | Backup |
|---|---|---|
| Research question, framing, narrative | Armando | Ryan |
| Industry / regulatory context (FDA, medtech, pharma) | Armando | — |
| Empirical strategy, econometric design | Ryan | Armando reviews |
| Data acquisition (FDA databases) | Armando | Ryan |
| Data acquisition (CRSP, Compustat, EDGAR, WRDS) | Ryan | — |
| Code, reproducibility, version control | Ryan | — |
| Paper drafting | Armando (sole author) | — |
| Tables, figures, regression output | Ryan | — |

## Mutual Exchange

This is explicitly a **two-way knowledge exchange**, not a one-way service relationship.

- **Armando provides Ryan with:** Industry context, regulatory mechanics, networking introductions, exposure to medtech/biotech operational realities, and grounded intuition about how FDA scrutiny *actually* affects firms in practice.
- **Ryan provides Armando with:** Econometric design support, empirical analysis, data engineering, archival data access via WRDS, and writing support on methods and results.

## Cadence

- **Recurring meeting:** *TBD — propose weekly 60-min Zoom or in-person.*
- **Async updates:** GitHub issues + brief Slack/email check-ins between meetings.
- **Meeting notes:** Logged in [`meetings/`](meetings/) by whoever runs the meeting.

## Decision Rules

- **Research design choices** that affect identification (sample, treatment definition, controls, estimator) → discussed jointly; Ryan recommends, both sign off in writing (commit message or meeting note).
- **Industry / regulatory interpretation** → Armando has final say.
- **Code, file structure, reproducibility practices** → Ryan has final say.
- **Manuscript narrative and framing** → Armando has final say; Ryan flags concerns that affect empirical defensibility.

## Authorship

The EDBA paper is **Armando's sole-authored work**. Ryan is not an author, advisor, or co-author and will not appear on the paper. Ryan's role is research assistance: econometric design, data engineering, and analytical support.

If at any future point this work — or a spinoff — moves toward an academic publication where Ryan's contributions would warrant authorship under field norms, that conversation happens then, in writing, and not before.

## Working Norms

- **No silent disagreement.** If one of us thinks something is wrong, say so on the PR / in the meeting. The cost of an awkward conversation is much lower than the cost of a flawed paper.
- **Reproducibility is non-negotiable.** Every number in the paper must trace back to a script in this repo.
- **Industry knowledge gets written down.** When Armando explains something about FDA process or medtech industry structure that informs an empirical choice, capture it in a meeting note or commit message so the rationale is durable.

## Tooling

- **Version control:** Git + GitHub (this repo)
- **Languages:** Python (data wrangling), R or Stata (regressions), LaTeX (paper)
- **Data warehouse:** WRDS via Ryan's UM credentials
- **Communication:** *TBD — Slack channel? Email thread?*

## Open Items

- [ ] Set first recurring meeting time
- [ ] Pick communication channel (Slack vs. email vs. Teams)
- [ ] Confirm authorship plan for any spinoff publications
- [ ] Agree on target submission outlet for the EDBA paper
- [ ] Confirm whether WRDS extracts can be shared with Armando under UM license
