# Literature Review Fix Log

**Document:** `Cuello_BUS813_Final Literature Review (1).pdf` (summer 2026 version)
**Source PDFs:** `../Articles Used for Summer 2026 Lit Review/` (45 of 45 cited academic sources; see `_File_Index.csv`)
**Started:** 2026-09-26

Page numbers are the **printed** page numbers at the bottom of each page (the PDF viewer's page number is one higher).

**Status:** Open · Done · Won't fix (with reason)

---

## A. Citation and reference errors (verified against the source PDFs)

| # | Location | Issue | Fix | Evidence | Status |
|---|---|---|---|---|---|
| A1 | References, p. 47; in-text pp. 21, 24 | The Karpoff et al. (2008) reference points to the wrong paper: *"The consequences to managers for cooking the books," JFE 88(88)*. The claims in the text (readjustment effect vs. reputation loss; reputation loss over 7.5x the legal penalties) come from a different paper by the same authors. The volume is also garbled ("88(88)"). | Replace with: Karpoff, J. M., D. S. Lee, and G. S. Martin (2008). The cost to firms of cooking the books. *Journal of Financial and Quantitative Analysis* 43(3), 581–612. | `Karpoff-et-al_2008_Cost-to-Firms-of-Cooking-the-Books.pdf`, abstract: "The reputation loss exceeds the legal penalty by over 7.5 times" | Open |
| A2 | p. 38 | The claim that CEO stock option pay "directly influences the incidence of product safety problems" is cited to Bundy et al. (2017). Bundy is a review that attributes this finding to **Wowak, Mannor & Wowak (2015)**. (There is also a stray closing parenthesis.) | Cite the original study: Wowak, A. J., M. J. Mannor, and K. D. Wowak (2015). Throwing caution to the wind: The effect of CEO stock option pay on the incidence of product safety problems. *Strategic Management Journal* 36(7), 1082–1092. Add to references and obtain the PDF. | `Bundy-et-al_2017_Crises-and-Crisis-Management.pdf`: cites Wowak, Mannor & Wowak (2015) for this point | Open |
| A3 | References, p. 46 | Anderson & Tan (2023) is listed as volume 12(**6**). The PDF shows Volume 12, **Issue 5**. | Change to 12(5), after confirming on the journal website. | `Anderson-Tan_2023_...pdf`, header: "Volume 12:05, 2023" | Open |
| A4 | References, p. 47 | Malik et al. (2025): the DOI number is printed where the volume/pages go ("01492063251345482"). | Format as an online-first article: *Journal of Management*, advance online publication. https://doi.org/10.1177/01492063251345482 | `Malik-et-al_2025_...pdf` header | Open |
| A5 | p. 34 | Christensen, Hail & Leuz (2021) is cited as having "observed" that optimistic forward-looking disclosures raise litigation risk. The paper says this in one passing sentence and itself cites Johnson et al. (2001) and Rogers et al. (2011). It's a secondary citation for the point. | Soften to "note" and cite the original evidence: Rogers, Van Buskirk & Zechman (2011), "Disclosure tone and shareholder litigation," *The Accounting Review* 86(6). Optional: Johnson, Kasznik & Nelson (2001), *JAR* 39(2). | `Christensen-et-al_2021_...pdf`: "forward-looking disclosures, especially when too optimistic, could expose firms to higher litigation risk (e.g., Johnson et al. 2001; Rogers et al. 2011)" | Open |
| A6 | Throughout | Lapré is rendered "Lapr ´e" / "Lapr´e" (accent not compiling). | Fix the LaTeX accent: `Lapr\'{e}`. | pp. 18, 47 | Open |

## B. Alignment of hypotheses and research design (from the design discussions)

| # | Location | Issue | Fix | Status |
|---|---|---|---|---|
| B1 | §4.4 (p. 41) vs. §6 (p. 45) | §4.4 names the core measures as **linguistic extremity, composition simplicity, and vocal tone**, but H2 tests **remedial specificity**, a construct the review never defines or cites. | Either develop remedial specificity in the body (tie it to Zavyalova et al.'s *technical actions* plus disclosure specificity), or restate H2 around the §4.4 measures. Recommended: keep H2 on remedial specificity and update §4.4 to match. | Open |
| B2 | §6, H2 | "Will positively moderate the negative CAR": a moderator changes a relationship, not an outcome. | Reword: *"The negative association between warning-letter severity and CAR is weaker when the firm's response exhibits high remedial specificity."* | Open |
| B3 | §6, H1 | Window T+0 to T+3 "prior to any public executive address." The FDA letter date is not public; the market learns of the letter from the firm's disclosure (median about 6 days after the letter) or the FDA's later posting. | Define day 0 as the **first public date** (firm 8-K/press release, or FDA posting for silent firms). Reword or drop "prior to any public executive address." | Open |
| B4 | §6 | **Severity** is developed in the text (device class, pending approvals put on hold, firm vulnerability) but appears in no hypothesis, although the design depends on it. | Add severity to H1 (more severe letters → more negative CAR) and to H2 (see B2). | Open |
| B5 | §4.2.5 (pp. 37–40) | The agency section (option wealth, CEO ownership) has no variable in the model. | Either frame it as a determinant of tactic choice (first-stage / endogeneity discussion) or shorten it to background. Needs ExecuComp if kept as analysis. | Open |
| B6 | §4.2.4, §4.4 | Vocal tone and delivery unscriptedness require earnings-call audio and transcripts the project doesn't have yet. | Move to limitations / future research unless transcripts are added. | Open |
| B7 | §4.2.4 | Composition simplicity is presented as a tactic, but the design discussion used readability as a **control**. | Decide one role and state it. | Open |
| B8 | Title, §1, throughout (9 uses) | "Hedge" means offsetting risk in finance and uncertainty language ("hedge words") in textual analysis, so readers may misread it. | Use "mitigate" or "attenuate" in the research question and hypotheses, or define "hedge" once explicitly. | Open |

## C. Content to add or decide

| # | Location | Item | Status |
|---|---|---|---|
| C1 | §4.2.4, methods discussion | Add Huang, Teoh & Zhang (2014), "Tone Management," *The Accounting Review* 89(3): the source for **abnormal tone**, which separates chosen tone from fundamentals. PDF: `../Additional Readings (Not Cited)/Huang-Teoh-Zhang_2014_Tone-Management.pdf`. | Open |
| C2 | §4.2.4 | Decide whether to cite Zheng, Yang & Chen (2023), *PLOS ONE*: stock-market reaction to product-harm crisis response strategies. The PDF is in the folder but not in the reference list. | Open |
| C3 | §2.1.1 | Optional: cite the Medical Device Amendments of 1976 (Public Law 94-295) directly alongside the FDA history page. The PDF is in the folder. | Open |
| C4 | §4.2.1 or §2 | Optional: the unused Deephouse & Suchman (2008) legitimacy chapter and Wang et al. (2016) "Trend Analysis of FDA Warning Letters" (both in `../Additional Readings (Not Cited)/`) could strengthen the legitimacy theory and FDA trend discussions. | Open |

## D. Typos and wording

| # | Location | Current | Fix | Status |
|---|---|---|---|---|
| D1 | p. 2 | "an may penalize firms" | "and may penalize firms" | Open |
| D2 | p. 2 | "this review aims to systematically compares" | "aims to systematically compare" | Open |
| D3 | p. 3 | "corporate leadership may navigates" | "may navigate" | Open |
| D4 | p. 9 | "Anderson and Tan (2023) highlight… Supporting this observation, Anderson and Tan (2023) report…" (a source supporting itself) | "Anderson and Tan (2023) further report…" | Open |
| D5 | p. 19 | "following recall announcements,." | "following recall announcements." | Open |
| D6 | p. 19 | "(Thirumalai and Sinha, 2011))" | Remove the extra parenthesis | Open |
| D7 | p. 29 | "informtaion" | "information" | Open |
| D8 | p. 35 | "limitations of these measurement tools remain paramount" (subject is "understanding") | "remains paramount" | Open |
| D9 | pp. 31–35 | The methods discussion shifts into past tense ("researchers had to…", "might achieve…") for current practice. | Use present tense for established methods. | Open |

---

## Change history

| Date | Change |
|---|---|
| 2026-09-26 | Literature folder reorganized; log moved to `literature/Lit Review Draft and Fix Log/`, paths updated. |
| 2026-09-26 | Log created. All 45 cited academic sources collected and renamed in `Articles Used for Summer 2026 Lit Review/`. Entries A1–A6, B1–B8, C1–C4, D1–D9 added. |
