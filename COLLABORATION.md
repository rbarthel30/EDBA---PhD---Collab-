# Collaboration Agreement

A working document for how Armando and Robert run this project together. Living document — update as the working relationship evolves.

## Roles

| Domain | Owner | Backup |
|---|---|---|
| Research question, framing, narrative | Armando | Robert |
| Industry / regulatory context (FDA, medtech, pharma) | Armando | — |
| Empirical strategy, econometric design | Robert | Armando reviews |
| Data acquisition (FDA databases) | Armando | Robert |
| Data acquisition (CRSP, Compustat, EDGAR, WRDS) | Robert | — |
| Code, reproducibility, version control | Robert | — |
| Paper drafting | Armando (lead) | Robert (methods sections) |
| Tables, figures, regression output | Robert | — |

## Mutual Exchange

This is explicitly a **two-way knowledge exchange**, not a one-way service relationship.

- **Armando provides Robert with:** Industry context, regulatory mechanics, networking introductions, exposure to medtech/biotech operational realities, and grounded intuition about how FDA scrutiny *actually* affects firms in practice.
- **Robert provides Armando with:** Econometric design support, empirical analysis, data engineering, archival data access via WRDS, and writing support on methods and results.

## Cadence

- **Recurring meeting:** *TBD — propose weekly 60-min Zoom or in-person.*
- **Async updates:** GitHub issues + brief Slack/email check-ins between meetings.
- **Meeting notes:** Logged in [`meetings/`](meetings/) by whoever runs the meeting.

## Decision Rules

- **Research design choices** that affect identification (sample, treatment definition, controls, estimator) → discussed jointly; Robert recommends, both sign off in writing (commit message or meeting note).
- **Industry / regulatory interpretation** → Armando has final say.
- **Code, file structure, reproducibility practices** → Robert has final say.
- **Manuscript narrative and framing** → Armando has final say; Robert flags concerns that affect empirical defensibility.

## Authorship

Armando is the lead author of the EDBA paper. Authorship order on any spinoff academic publications to be agreed in writing before submission. Both parties' contributions documented in a CRediT-style statement.

## Working Norms

- **No silent disagreement.** If one of us thinks something is wrong, say so on the PR / in the meeting. The cost of an awkward conversation is much lower than the cost of a flawed paper.
- **Reproducibility is non-negotiable.** Every number in the paper must trace back to a script in this repo.
- **Industry knowledge gets written down.** When Armando explains something about FDA process or medtech industry structure, Robert (or Armando) captures it in `notes-from-armando/` so it doesn't get lost.

## Tooling

- **Version control:** Git + GitHub (this repo)
- **Languages:** Python (data wrangling), R or Stata (regressions), LaTeX (paper)
- **Data warehouse:** WRDS via Robert's UM credentials
- **Communication:** *TBD — Slack channel? Email thread?*

## Open Items

- [ ] Set first recurring meeting time
- [ ] Pick communication channel (Slack vs. email vs. Teams)
- [ ] Confirm authorship plan for any spinoff publications
- [ ] Agree on target submission outlet for the EDBA paper
- [ ] Confirm whether WRDS extracts can be shared with Armando under UM license
