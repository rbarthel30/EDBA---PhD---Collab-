# Warning-Letter Full Texts — Replication Instructions

**Dataset:** `data/warning_letters/` (one text file + one HTML file per letter, plus a manifest)
**Produced by:** [`scripts/23_fetch_warning_letter_texts.py`](../../scripts/23_fetch_warning_letter_texts.py)
**Maintainer:** Ryan Barthel · **First built:** 2026-10-13

This folder holds the **full text of the FDA warning letters** in our sample:
every medical-device warning letter that the project links to a listed
(Compustat) company. These are the letters behind the `n_warning_letter`
counts in `data/combined_9_28_26.csv`. The rest of this page explains where
each letter came from, how we confirmed it is the right letter, and how to
rebuild the folder from scratch.

> **Archived (pre-2016) letters.** FDA's live site only carries letters from
> 2021 on; older letters survive only in web archives. We recovered
> **126 of 160** letters issued 2008–2015 (as of 2026-10-19):
> - **2008–2012: 87 of 98**, nearly complete.
> - **2013–2015: 39 of 62**, the main gap (FDA's archived indexes for these
>   years are incomplete).
>
> 112 of the 126 come from **Common Crawl** copies of FDA's old site.
>
> **Totals:** 168 of the 206 project letters, plus 7 of 10 extra letters
> Armando requested (see Section 6).

---

## 1. What is in this folder

| Item | What it is |
|---|---|
| `text/<case_id>_<firm>_<date>.txt` | **The letter itself as plain text.** This is the file to read or code. |
| `html/<case_id>_<firm>_<date>.html` | The web page exactly as FDA published it (the original source, kept for audit). |
| `warning_letter_texts_manifest_<date>.csv` | **One row per letter.** Who got it, when, which listed parent it is linked to, where the text came from, and any review flag. Open this first. |
| `warning_letter_text_candidates_<date>.csv` | Audit trail: every web page considered for every letter, with the checks it passed or failed. |

File names start with the **Case ID**, which is the FDA Data Dashboard's
`Case/Injunction ID`. On FDA's website the same number appears as
**"MARCS-CMS"** or **"CMS #"**, and the two match exactly.

### Manifest columns

| Column | Meaning |
|---|---|
| `case_id` | FDA Case/Injunction ID = MARCS-CMS number |
| `fei_number`, `recipient_name_fda`, `recipient_state`, `recipient_country` | Letter recipient as the FDA Data Dashboard records it |
| `action_taken_date`, `letter_year` | Dashboard date of the letter |
| `gvkey`, `company_name_compustat` | The **listed parent** the letter is attributed to. A letter to a subsidiary or acquired firm counts for the parent (the 9/28 crosswalk decision). |
| `publicly_traded_in_letter_year` | 1 if the parent had a Compustat market cap that fiscal year (the script-14 test). 34 of the 206 letters are 0, usually because the firm had been taken private or was not yet listed. |
| `text_found` | 1 if the letter text was retrieved |
| `source` | `fda.gov (live)`, `Wayback Machine (fda.gov new URL scheme)`, `Common Crawl (fda.gov old URL scheme)` or `Wayback Machine (fda.gov old URL scheme)` (see Section 2) |
| `source_url` | The fda.gov address the letter was published at |
| `archive_capture` | Exactly which archived copy was used. Wayback: a link that opens that capture. Common Crawl: crawl name, archive file and byte position. The saved `html/` file is that copy. |
| `letter_date_in_text` | The date printed on the letter that is closest to the dashboard date |
| `date_gap_days` | Days between that printed date and the dashboard date |
| `case_id_in_text` | 1 if the letter itself prints the Case ID (letters from about 2014 on usually do) |
| `listing_company` | For old letters: the company name on FDA's own index page that linked to the letter |
| `text_chars` | Length of the extracted text |
| `review_flag` | Blank = clean. Otherwise it says what to double-check (see Section 3). |

---

## 2. Where the letter texts come from

All texts are **FDA's own published pages**. We never use third-party
transcriptions. FDA keeps only recent letters on its live website, so older
letters come from two public web archives that saved copies of fda.gov while
the letters were still posted: the **Internet Archive's Wayback Machine** and
**Common Crawl** (a nonprofit archive of the web, published for research use).

| Letters issued | Where the text comes from | How we find the right page |
|---|---|---|
| 2021 to present | **fda.gov, live** Warning Letters page | Each letter's web address ends in `-<Case ID>-<date>`, so the Case ID finds it directly. |
| about 2014 to 2020 | **Wayback Machine** copy of the same kind of fda.gov page (FDA has since removed them) | Same: the Case ID is in the web address. |
| 2008 to about 2016 | **Common Crawl** copy (Wayback as backup) of FDA's older site (`fda.gov/ICECI/EnforcementActions/WarningLetters/<year>/ucmNNNNNN.htm`) | These addresses have no Case ID. We read FDA's archived **year-by-year index pages** (issue date, company, issuing office, link) and match on **issue date plus company name**. |

**Why two archives?** The Wayback Machine only lets a user make a few dozen
requests before blocking them for an hour or more, which is too slow for the
~500 old index pages. Common Crawl serves its copies from a content network
built for bulk research downloads, and one Common Crawl snapshot shows each
year's index pages as they stood on a single day, so no letters slip between
pages captured at different times.

**Why not FDA's own archive?** FDA's official archive of its old website
(`wayback.archive-it.org/7993`) puts a bot-verification page in front of every
request, so we do not use it. The two public archives hold the same FDA pages.

---

## 3. How we confirm each text is the right letter

One Case ID can carry several documents: the **warning letter**, a later
**close-out letter** (FDA saying the problems are fixed), and sometimes the
**firm's response letter**, which FDA also posts. The script reads every
candidate page and keeps a page only if all of these hold:

1. **It is the warning letter itself.** Close-out letters are recognized by
   FDA's standard wording ("has completed an evaluation of your corrective
   actions"), and response letters by FDA's page label. One trap: FDA
   **re-labels** a page "CLOSEOUT LETTER" once a case closes, even though the
   page still shows the original warning letter. So the script reads the
   letter body, not the label.
2. **It is this letter.** Either the letter prints the **Case ID** (CMS #),
   which identifies it uniquely, or it **names the recipient** and carries a
   date within 31 days of the Data Dashboard date. The dashboard is often a
   day or a few days off the letter's own date, so gaps over 7 days are
   allowed but flagged. (One dashboard date is plainly wrong: Ocular
   Therapeutix's 2018 letter is dated 2020-09-02 there, the date of its
   close-out letter. The current script accepts it on its Case ID; this
   snapshot predates that rule, so it is still listed as not found.)
3. For old-site letters, **FDA's own index page** must list the letter under
   the same company name (an exact match after removing "Inc.", punctuation
   and similar, or a close fuzzy match, which is flagged), or under a
   **former name of the same establishment** (next point).
4. **Former names.** The Data Dashboard shows each establishment's CURRENT
   name, but letters went to whoever ran the site at the time. A 2008 letter
   to I-Flow appears in the dashboard as "Avanos Medical"; a 2012 letter to
   McNeil-PPC as "Kenvue". The script takes each establishment's earlier names
   from FDA's own recall records (same FEI number) and also accepts those.
   Every letter found this way is flagged `ADDRESSED TO FORMER NAME`; see the
   warning below.
5. **Letters missing from FDA's index.** For some years (2013 and 2015–16 above
   all) the archived index pages are incomplete. For letters still not found,
   the script reads every archived letter page that no index page lists and
   indexes it by its own title line ("Medtronic, Inc. 7/17/12"). These must
   carry an explicit WARNING LETTER heading and are flagged. (This step was
   added after this snapshot and was stopped before it finished, so no letter
   in this snapshot was found this way. See Section 5.)

> ⚠️ **Check the gvkey on `ADDRESSED TO FORMER NAME` letters.** Some went to a
> firm that the listed parent did not own yet. Examples: "3M" June 2010 was
> addressed to Arizant (3M bought it in Oct 2010), "ZOLL" 2010 to Cardiac
> Science and Impact Instrumentation (bought by ZOLL years later), "Varian"
> 2010 to Endocare, and "Evoqua" 2014 to Mar Cor Purification. The project
> crosswalk (9/28) attributes these letters to the CURRENT owner, so they may
> be wrongly counted as events for that firm. This affects the event panel,
> not just this folder.

When several pages pass, the script prefers one that prints the Case ID, then
the closest date, then an exact name match, then the live site over an
archive copy.

**What `review_flag` means:**
- `letter date Nd from dashboard date`: the letter's own date is more than 7 days from the dashboard date.
- `case ID not printed; matched on date+name`: normal for pre-2014 letters. The match rests on FDA's index page plus the date and name checks.
- `fuzzy listing name match`: FDA's index wrote the company name a little differently (for example "Corp" vs "Corporation" with extra words, or a division of the firm).
- `ADDRESSED TO FORMER NAME`: see the warning above.
- `not in FDA's archived index pages; found by the letter page's own title`: see point 5.
- `SAME PAGE AS ANOTHER LETTER`: the dashboard gives one letter several Case IDs (e.g. LCA-Vision, 9 Oct 2009, three Case IDs), so the same text serves each.
- `NOT FOUND`: no surviving copy could be found or loaded (Section 5).

---

## 4. How to rebuild it

From the repository root:

```bash
python scripts/23_fetch_warning_letter_texts.py
```

- **Inputs** (already in the repo or on Ryan's machine): the Data Dashboard
  file (script 03), the unified gvkey crosswalk (script 12), and the Compustat
  annual file (`data/raw/compustat_funda_2026-09-28.csv`, licensed and not in
  the repo; it is needed only for the `publicly_traded_in_letter_year` flag
  and the letter count check).
- **Run time:** about 1–3 hours on a fresh machine. The Wayback Machine
  throttles heavily and blocks bursts with "HTTP 429"
  errors. The script spaces its requests 8 seconds apart and, when blocked,
  goes quiet for 15, then 30, then 60 minutes before trying again. Everything it downloads is cached in
  `%LOCALAPPDATA%\edba_fda_cache\warning_letter_text\`, so a re-run (or a run
  that was interrupted) finishes in seconds.
- `--refresh` re-downloads the fda.gov, Wayback and Common Crawl indexes. Use
  it only to pick up newer letters, because the archive copies themselves do
  not change.
- When archive.org blocks the run (HTTP 429), the script stops asking it for
  the rest of that run and lists the affected letters as `NOT FOUND`. Simply
  re-run it a few hours later (cached pages are reused), or add
  `--wayback-wait` to sit out the block.
- Extra input: `data/raw/fda_device_recalls_2026-07-19.csv` (script 10, not in
  the repo; re-download with `python scripts/10_fetch_part806_corrections_removals.py`)
  supplies the establishments' former names.

The script checks that it starts from exactly **206 letters**, the same set
as the 9/28 combined dataset. If the crosswalk changes, that check fails on
purpose, so the letter set never drifts unnoticed.

---

## 5. First snapshot (2026-10-13; superseded by Section 6)

The download was **stopped early at Ryan's request**; this folder holds what
had been collected and verified by then.

| | Letters |
|---|---:|
| Device warning letters linked to a listed firm (the target set) | 206 |
| **Full text retrieved and verified** | **157** (76%) |
| ... of which the parent was publicly traded in the letter year | 136 of 172 |
| ... firms with at least one letter text | 93 of 117 |
| Not found | 49 |

**By source:** 104 from Common Crawl copies of FDA's pre-2017 site, 28 from
Wayback copies of 2014–2020 pages, 25 from the live fda.gov site.
73 letters print their Case ID; the other 84 (mostly pre-2014) were matched on
FDA's own index entry, issue date and recipient name.

**By year (found / target):** 2008 4/4 · 2009 18/20 · 2010 25/26 ·
2011 19/26 · 2012 20/22 · 2013 10/26 · 2014 13/21 · 2015 6/15 · 2016 1/4 ·
2017–2026 41/42.

**Flags on the 157:** 69 carry no flag. 23 were addressed to a former name of
the establishment (see the ⚠️ box in Section 3), 11 matched FDA's index on a
close but not exact name, 7 share one page with another Case ID, and 4 have a
letter date more than 7 days from the dashboard date.

**Why 49 are missing:**
- **Wayback blocked (11, mostly 2014).** FDA's index lists them, but the only
  surviving copy is in the Wayback Machine, which had blocked us. A re-run
  once the block lifts should recover most of them.
- **No match in the archived FDA index (34, mostly 2011, 2013, 2015–16).** The
  archived index pages for these years miss many letters, and some firms may
  appear under names we cannot link. The title-search step (Section 3,
  point 5) targets exactly these letters but was stopped before finishing.
- **Only the close-out letter survives (3).** Ortho Clinical Diagnostics 2015,
  Spectranetics 2016, Orthosoft 2016: the archives hold the later close-out
  letter, not the warning letter itself.
- **Dashboard date error (1).** Ocular Therapeutix (Section 3, point 2).

To continue, re-run `python scripts/23_fetch_warning_letter_texts.py`. Pages
already downloaded are cached, and the run adds whatever it can still find.
Note that a re-run also applies one more check added after this snapshot: it
flags every letter whose printed recipient differs from the dashboard name,
even when the letter was found by its Case ID. For example, the October 2021
"ICU Medical" letter is addressed to Smiths Medical, which ICU bought in
January 2022.

---

## 6. Update 2026-10-19: Armando's 27 requested letters

Re-run with `--case-ids` (search only the listed case numbers and merge into
the manifest) and `--wayback-wait`, after archive.org's block had lifted.

- **17 letters in our 206** that neither his PDFs nor our first snapshot had:
  **11 found**, 6 still missing (Medivators 2009, LeMaitre 2010, Leica 2011,
  St. Jude 2012-06-05, ICU Medical Costa Rica 2012, Dentsply 2013).
- **10 letters in his sample but outside our 206** (no Compustat link): added
  with `in_project_sample = 0` and blank gvkey. **7 found** (Veolia, AMO
  Uppsala, Isomedix ×2, Canon, NCS Pearson, LivaNova); 3 still missing
  (EMD Millipore 2009, **Labcorp-PMD 2011**, Valeant 2012).
- For hand-requested case numbers only, the script also accepts an FDA index
  entry dated within 3 days that shares a distinctive word with the firm's
  name (e.g. "Steris Isomedix Services" for "Isomedix Operations"). Such
  matches are flagged, and the letter text must still pass every check.
- **Labcorp 2011:** not in any archived FDA index page (none lists Labcorp
  near July 2011), and no cached archived letter page mentions it. The only
  Labcorp letters found are from 2007 (ViroMed) and September 2008. FDA may
  never have posted the 2011 letter; if so, a FOIA request is the remaining
  route.

The manifest now has 216 rows (206 + 10). 34 of the found letters are
flagged `ADDRESSED TO …` (sent to a different or former firm name than the
dashboard shows).

