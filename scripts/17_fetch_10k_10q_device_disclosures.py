# =============================================================
# Script: 17_fetch_10k_10q_device_disclosures.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Build a periodic-filing disclosure panel in the spirit of Bozanic,
#          Dietrich & Johnson (2017): for the gvkey-linked device firms in the
#          main panel, collect their 10-K and 10-Q filings and measure how much
#          each filing DISCUSSES the three FDA monitoring/action events, as
#          opposed to merely listing them as hypothetical risks.
#
#              warning_letter  - FDA Warning Letter
#              recall          - recall / correction & removal (Part 806)
#              adverse_event   - adverse event / Medical Device Report (803)
#
#          This is a SEPARATE panel from the event/8-K datasets ("10K_10Q_
#          devices"); it is joined to the treatment panel later on gvkey/CIK.
#
# ---------------------------------------------------------------------------
# TWO MEASUREMENT PROBLEMS, TWO DELIBERATE CHOICES
#
#   (A) WHICH TEXT. A 10-K is ~400k characters; most of it is financial
#       statements, exhibits and boilerplate irrelevant to disclosure framing.
#       We keep only the two narrative sections where these events are
#       discussed: RISK FACTORS (Item 1A) and MD&A (Item 7 in a 10-K, Item 2
#       in a 10-Q). Sections are located by the "widest-span" rule (below),
#       which is robust to the table of contents and to cross-references.
#
#       Note: Item 1A Risk Factors became required only for fiscal years
#       ending on/after 1 Dec 2005, so Risk-Factor coverage effectively starts
#       in 2006. The default sample therefore begins in 2005 and the RF-absent
#       flag records filings with no Item 1A.
#
#   (B) DISCUSSION vs BOILERPLATE. Risk Factors are dominated by hypothetical
#       language - "we MAY receive a warning letter", "a recall COULD have a
#       material adverse effect". That is not disclosure of an event; it is a
#       generic risk disclaimer. A raw term count cannot tell the two apart.
#
#       So each mention is scored SUBSTANTIVE only when its sentence carries a
#       marker of an ACTUAL event: an agentive past-tense verb tying the firm
#       to the event ("received", "initiated a recall of", "was issued"), a
#       definite reference ("the warning letter", "this recall"), or a
#       specific date. A sentence that contains only the term plus modal
#       hedging ("may", "could", "if") is counted as a mention but NOT as
#       substantive. Both counts are kept, per section, so the boilerplate
#       share is measurable rather than assumed.
# ---------------------------------------------------------------------------
#
# SAMPLE: the 140 gvkey-linked device firms in gvkey_year_event_panel that
#   carry a CIK. 10-K and 10-Q filings, default 2005 onward.
#
# Inputs:  data/processed/gvkey_year_event_panel_<DATE>.csv   (script 14; gvkey+cik)
# Outputs: data/processed/10k_10q_devices_<DATE>.csv          (the panel)
#          output/tables/10k_10q_descriptives_<DATE>.md
#   Section text is cached OUTSIDE the repo (see SECTION_CACHE) so re-scoring
#   never re-fetches.
#
# Usage:   python scripts/17_fetch_10k_10q_device_disclosures.py
#          python scripts/17_fetch_10k_10q_device_disclosures.py --since 2005
#          python scripts/17_fetch_10k_10q_device_disclosures.py --limit 5   (smoke test)
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import os
import re
import sys
import glob
import html
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
TABLES_DIR = REPO_ROOT / "output" / "tables"

SEC_UA = {"User-Agent": os.environ.get(
    "SEC_USER_AGENT", "University of Miami Research rbarthel15@gmail.com")}
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
REQUEST_SLEEP = 0.13
DEFAULT_SINCE = 2005          # Item 1A Risk Factors required for FYE >= 2005-12-01
FORMS = {"10-K", "10-Q"}

# Section text cache, OUTSIDE OneDrive (same rationale as scripts 11/15):
# fetching is the slow part, scoring is instant, so caching the extracted
# section text lets the classifier be revised without re-fetching.
_default_cache = (Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
                  / "edba_fda_cache" / "edgar_10kq_sections")
SECTION_CACHE = Path(os.environ.get("EDGAR_10KQ_CACHE", _default_cache))


# =============================================================
# STEP 1. Event vocabulary and substantive/boilerplate markers
# =============================================================
EVENT_TERMS = {
    "warning_letter": re.compile(r"\bwarning\s+letter", re.I),
    "recall": re.compile(
        r"\brecall(?:s|ed|ing)?\b"
        r"|\bcorrection[s]?\s+and\s+removal[s]?\b"
        r"|\bfield\s+(?:safety\s+)?(?:corrective\s+)?action"
        r"|\bfield\s+safety\s+notice", re.I),
    "adverse_event": re.compile(
        r"\badverse\s+event"
        r"|\bmedical\s+device\s+report(?:ing|s)?\b"
        r"|\bMDR\b", re.I),
}

# A sentence discusses an ACTUAL event if it ties the firm to a concrete
# occurrence. Three independent signals, any one of which suffices.
ACTUAL_MARKERS = re.compile(
    # agentive past-tense verbs of receiving / acting
    r"\breceiv(?:ed|ing)\b|\bwas\s+issued\b|\bwere\s+issued\b|\bissued\s+(?:to|by|a)\b"
    r"|\bnotified\b|\binitiat(?:ed|ing)\b|\bannounc(?:ed|ing)\b|\bconduct(?:ed|ing)\b"
    r"|\bcompleted\b|\brecalled\b|\bcorrect(?:ed|ive\s+action\s+was)\b"
    r"|\bremediat(?:ed|ion\s+of)\b|\bresolved\b|\bclos(?:ed|ure\s+of)\b"
    r"|\bsubmitted\s+(?:a\s+)?response\b|\brespond(?:ed|ing)\s+to\b"
    # definite / possessive reference to a specific instance
    r"|\bthe\s+warning\s+letter\b|\bthis\s+recall\b|\bthe\s+recall\b|\bour\s+recall\b"
    r"|\bthe\s+FDA\s+warning\s+letter\b|\bvoluntary\s+recall\s+of\b"
    # a specific calendar anchor
    r"|\bin\s+(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}\b"
    r"|\bduring\s+(?:the\s+)?(?:quarter|year|period|three|six|nine)\b",
    re.I)

# Hedging / hypothetical language. Recorded for the boilerplate share; a
# sentence with hedging AND no actual marker is boilerplate.
HEDGE_MARKERS = re.compile(
    r"\bmay\b|\bcould\b|\bmight\b|\bwould\b|\bif\s+we\b|\bin\s+the\s+event\b"
    r"|\brisk(?:s)?\s+that\b|\bno\s+assurance\b|\bfrom\s+time\s+to\s+time\b"
    r"|\bcould\s+result\b|\bcould\s+have\s+a\s+material\b|\bsubject\s+to\b"
    r"|\bpotential(?:ly)?\b|\bmay\s+be\s+required\b|\bwere\s+to\b", re.I)


def latest(directory: Path, pattern: str) -> Path:
    """Return the most recent date-stamped file matching a glob pattern."""
    hits = sorted(glob.glob(str(directory / pattern)))
    if not hits:
        raise FileNotFoundError(f"No file matches {pattern} in {directory}")
    return Path(hits[-1])


def sec_get(url: str) -> requests.Response:
    """GET against SEC with the required UA, throttling, and 429 back-off."""
    for attempt in range(4):
        resp = requests.get(url, headers=SEC_UA, timeout=90)
        if resp.status_code == 429:
            time.sleep(2 + 3 * attempt)
            continue
        time.sleep(REQUEST_SLEEP)
        return resp
    return resp


# =============================================================
# STEP 2. Filing discovery per firm
# =============================================================
def list_filings(cik: int, since: int) -> list:
    """
    Return every 10-K / 10-Q for a CIK since `since`, across ALL history.

    The submissions JSON holds only the most recent ~1,000 filings inline; the
    remainder are sharded into additional files listed under filings.files.
    Both are read, so a long-lived filer's early-2000s filings are not lost.
    """
    resp = sec_get(SUBMISSIONS_URL.format(cik=cik))
    if resp.status_code != 200:
        return []
    base = resp.json()
    blocks = [base["filings"]["recent"]]
    for extra in base["filings"].get("files", []):
        r = sec_get(f"https://data.sec.gov/submissions/{extra['name']}")
        if r.status_code == 200:
            blocks.append(r.json())

    out = []
    for blk in blocks:
        forms = blk.get("form", [])
        for i, form in enumerate(forms):
            if form not in FORMS:
                continue
            fdate = blk["filingDate"][i]
            if int(fdate[:4]) < since:
                continue
            out.append({
                "cik": cik, "form": form,
                "accession": blk["accessionNumber"][i],
                "filing_date": fdate,
                "report_date": blk["reportDate"][i],
                "primary_document": blk["primaryDocument"][i],
            })
    return out


# =============================================================
# STEP 3. Section extraction (Risk Factors + MD&A)
# =============================================================
def strip_html(raw: str) -> str:
    """Markup -> normalized plain text."""
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html.unescape(txt).replace("\xa0", " ")
    return re.sub(r"\s+", " ", txt).strip()


def widest_span(text: str, start_pat: str, end_pats: list) -> str:
    """
    Return the text of a section delimited by an item header.

    An item header ("Item 1A") appears at least twice: once in the table of
    contents and once at the real section. The TOC copies sit only a few
    characters apart, while the real section spans thousands. So among all
    (start, nearest-following-end) pairs, the one with the LARGEST gap is the
    real section. This is robust to the TOC and to stray cross-references
    without needing to model document structure.
    """
    starts = [m.start() for m in re.finditer(start_pat, text, re.I)]
    ends = []
    for pat in end_pats:
        ends += [m.start() for m in re.finditer(pat, text, re.I)]
    ends.sort()
    best, best_len = "", 0
    for s in starts:
        nxt = [e for e in ends if e > s]
        if not nxt:
            continue
        span = nxt[0] - s
        if span > best_len:
            best_len, best = span, text[s:nxt[0]]
    return best


def extract_sections(text: str, form: str) -> dict:
    """
    Pull Risk Factors and MD&A for the given form.

    10-K: Item 1A -> Item 1B/Item 2 ; Item 7 -> Item 7A/Item 8.
    10-Q: Part II Item 1A -> Item 2/Item 6 ; Item 2 -> Item 3/Item 4.
    A section shorter than 400 characters is treated as absent (a boilerplate
    "there have been no material changes" cross-reference, not a real section).
    """
    if form == "10-K":
        rf = widest_span(text, r"item\s*1a[\.\s]",
                         [r"item\s*1b[\.\s]", r"item\s*2[\.\s]"])
        mda = widest_span(text, r"item\s*7[\.\s](?!a)",
                          [r"item\s*7a[\.\s]", r"item\s*8[\.\s]"])
    else:  # 10-Q
        rf = widest_span(text, r"item\s*1a[\.\s]",
                         [r"item\s*2[\.\s]", r"item\s*6[\.\s]",
                          r"item\s*5[\.\s]"])
        mda = widest_span(text, r"item\s*2[\.\s]",
                          [r"item\s*3[\.\s]", r"item\s*4[\.\s]"])
    return {
        "risk_factors": rf if len(rf) >= 400 else "",
        "mda": mda if len(mda) >= 400 else "",
    }


# =============================================================
# STEP 4. Substantive-vs-boilerplate scoring
# =============================================================
# A modal or conditional in the short span IMMEDIATELY BEFORE the event term
# marks that occurrence as hypothetical ("...they may issue [warning letters]",
# "if a [recall] were required"). Checked locally, not sentence-wide.
LOCAL_HEDGE = re.compile(
    r"\b(?:may|could|might|would|can|will|if|should|potential(?:ly)?|"
    r"possible|possibly|any|such|other|risk\s+of|event\s+of)\b", re.I)
PRE_WINDOW = 55       # chars before the term to test for local hedging
CONTEXT_WINDOW = 140  # chars each side to test for an actual-event marker


def score_section(section_text: str) -> dict:
    """
    Count, per event type, total mentions and SUBSTANTIVE mentions.

    OCCURRENCE-based, not sentence-based. Sentence segmentation is unreliable
    in EDGAR text - registered-trademark glyphs, abbreviations and dropped
    spaces routinely glue a hypothetical clause to an adjacent factual one,
    which made a whole-sentence rule mislabel boilerplate as substantive. So
    each occurrence is judged in its own local window:

      * mention       = any occurrence of the event term.
      * substantive   = the term is NOT locally hedged (no modal/conditional
                        in the ~55 chars before it) AND an actual-event marker
                        (past-tense receipt/action verb, definite reference, or
                        a specific date) appears within ~140 chars around it.
      * hedged        = locally hedged; the residual of a mention that is
                        neither substantive nor hedged is a bare factual list.

    This correctly keeps "in 2010 we initiated a voluntary recall ... which
    could have a material adverse effect" (trailing hedge, real event) while
    dropping "they may mandate corrective actions and issue warning letters"
    (leading modal, hypothetical).
    """
    out = {e: {"mentions": 0, "substantive": 0, "hedged": 0} for e in EVENT_TERMS}
    if not section_text:
        return out
    n = len(section_text)
    for ev, pat in EVENT_TERMS.items():
        for mt in pat.finditer(section_text):
            out[ev]["mentions"] += 1
            pre = section_text[max(0, mt.start() - PRE_WINDOW):mt.start()]
            ctx = section_text[max(0, mt.start() - CONTEXT_WINDOW):
                               min(n, mt.end() + CONTEXT_WINDOW)]
            locally_hedged = bool(LOCAL_HEDGE.search(pre))
            has_actual = bool(ACTUAL_MARKERS.search(ctx))
            if has_actual and not locally_hedged:
                out[ev]["substantive"] += 1
            elif locally_hedged:
                out[ev]["hedged"] += 1
    return out


# =============================================================
# STEP 5. Fetch + score one filing (cached)
# =============================================================
def process_filing(f: dict) -> dict:
    """Fetch (or load cached) sections for one filing and score them."""
    SECTION_CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{f['accession'].replace('-', '')}".replace("/", "_")
    cache_file = SECTION_CACHE / f"{key}.json"

    if cache_file.exists():
        sections = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        acc = f["accession"].replace("-", "")
        url = ARCHIVE_DOC.format(cik=int(f["cik"]), acc=acc,
                                 doc=f["primary_document"])
        resp = sec_get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        text = strip_html(resp.content.decode("utf-8", errors="replace"))
        sections = extract_sections(text, f["form"])
        cache_file.write_text(json.dumps(sections), encoding="utf-8")

    rf = score_section(sections["risk_factors"])
    mda = score_section(sections["mda"])

    rec = {
        "cik": int(f["cik"]), "form": f["form"],
        "accession": f["accession"], "filing_date": f["filing_date"],
        "report_date": f["report_date"],
        "filing_year": int(f["filing_date"][:4]),
        "has_risk_factors": bool(sections["risk_factors"]),
        "has_mda": bool(sections["mda"]),
        "rf_chars": len(sections["risk_factors"]),
        "mda_chars": len(sections["mda"]),
    }
    # One column block per event x section, plus filing-level substantive total.
    for ev in EVENT_TERMS:
        rec[f"rf_{ev}_mentions"] = rf[ev]["mentions"]
        rec[f"rf_{ev}_substantive"] = rf[ev]["substantive"]
        rec[f"mda_{ev}_mentions"] = mda[ev]["mentions"]
        rec[f"mda_{ev}_substantive"] = mda[ev]["substantive"]
        rec[f"{ev}_substantive_total"] = (rf[ev]["substantive"]
                                          + mda[ev]["substantive"])
        rec[f"{ev}_mentions_total"] = rf[ev]["mentions"] + mda[ev]["mentions"]
    return rec


# =============================================================
# STEP 6. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    since = DEFAULT_SINCE
    if "--since" in sys.argv:
        since = int(sys.argv[sys.argv.index("--since") + 1])
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    print("=" * 64)
    print("10-K / 10-Q device disclosure panel (Bozanic-style)")
    print(f"Snapshot date: {snapshot_date} | filings from {since}")
    print("=" * 64)

    # --- 6a. Firm universe from the main panel. ---
    panel = pd.read_csv(latest(PROCESSED_DIR, "gvkey_year_event_panel_*.csv"),
                        low_memory=False)
    firms = (panel[panel["cik"].notna()]
             .drop_duplicates("gvkey")[["gvkey", "cik",
                                        "company_name_compustat"]])
    firms["cik"] = firms["cik"].astype(int)
    if limit:
        firms = firms.head(limit)
    print(f"[1/3] Firm universe: {len(firms):,} device firms with a CIK")

    # --- 6b. Discover filings. ---
    print("[2/3] Listing 10-K/10-Q filings ...")
    cik_to_gvkey = dict(zip(firms["cik"], firms["gvkey"]))
    cik_to_name = dict(zip(firms["cik"], firms["company_name_compustat"]))
    all_filings = []
    for i, cik in enumerate(firms["cik"], start=1):
        fs = list_filings(cik, since)
        all_filings.extend(fs)
        if i % 25 == 0 or i == len(firms):
            print(f"    {i}/{len(firms)} firms scanned, "
                  f"{len(all_filings):,} filings so far")
    print(f"    {len(all_filings):,} filings to fetch "
          f"(~{len(all_filings) * REQUEST_SLEEP / 60:.0f} min minimum)")

    # --- 6c. Fetch + score. ---
    print("[3/3] Fetching sections and scoring ...")
    records, n_fail = [], 0
    for i, f in enumerate(all_filings, start=1):
        try:
            rec = process_filing(f)
            rec["gvkey"] = cik_to_gvkey.get(rec["cik"])
            rec["company"] = cik_to_name.get(rec["cik"])
            records.append(rec)
        except Exception as exc:  # noqa: BLE001 - one bad filing must not kill the run
            n_fail += 1
            if n_fail <= 5:
                print(f"      failed {f['accession']}: {exc}")
        if i % 250 == 0:
            print(f"    {i:,}/{len(all_filings):,} processed ({n_fail} failures)")

    df = pd.DataFrame(records)
    if df.empty:
        raise RuntimeError("No filings were successfully processed.")
    lead = ["gvkey", "cik", "company", "form", "filing_date", "filing_year"]
    df = df[lead + [c for c in df.columns if c not in lead]]
    df = df.sort_values(["gvkey", "filing_date"])

    out_path = PROCESSED_DIR / f"10k_10q_devices_{snapshot_date}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    processed {len(df):,} filings ({n_fail} failures)")
    print(f"    panel -> {out_path.relative_to(REPO_ROOT)}")

    md = describe(df, snapshot_date)
    md_path = TABLES_DIR / f"10k_10q_descriptives_{snapshot_date}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"    descriptives -> {md_path.relative_to(REPO_ROOT)}\n")
    sys.stdout.reconfigure(errors="replace")
    print(md)
    print("Done.")


# =============================================================
# STEP 7. Descriptives
# =============================================================
def describe(df: pd.DataFrame, snapshot_date: str) -> str:
    """Descriptive block written to output/tables/."""
    lines = []
    add = lines.append
    events = list(EVENT_TERMS)

    add(f"# 10-K / 10-Q device disclosure panel ({snapshot_date})\n")
    add("| Statistic | Value |")
    add("|:---|---:|")
    add(f"| Filings | {len(df):,} |")
    add(f"| Firms (gvkey) | {df['gvkey'].nunique():,} |")
    add(f"| 10-K | {int((df['form'] == '10-K').sum()):,} |")
    add(f"| 10-Q | {int((df['form'] == '10-Q').sum()):,} |")
    add(f"| Filing-year range | {int(df['filing_year'].min())}-"
        f"{int(df['filing_year'].max())} |")
    add(f"| With Risk Factors section | "
        f"{int(df['has_risk_factors'].sum()):,} "
        f"({df['has_risk_factors'].mean():.0%}) |")
    add(f"| With MD&A section | {int(df['has_mda'].sum()):,} "
        f"({df['has_mda'].mean():.0%}) |\n")

    add("## Event discussion: mentions vs SUBSTANTIVE (boilerplate-filtered)\n")
    add("| Event | Filings w/ mention | Filings w/ substantive | "
        "Total mentions | Total substantive | Substantive share |")
    add("|:---|---:|---:|---:|---:|---:|")
    for ev in events:
        m = df[f"{ev}_mentions_total"]
        s = df[f"{ev}_substantive_total"]
        share = s.sum() / m.sum() if m.sum() else 0
        add(f"| {ev} | {int((m > 0).sum()):,} | {int((s > 0).sum()):,} | "
            f"{int(m.sum()):,} | {int(s.sum()):,} | {share:.0%} |")
    add("")

    add("## Substantive mentions by section\n")
    add("| Event | Risk Factors | MD&A |")
    add("|:---|---:|---:|")
    for ev in events:
        add(f"| {ev} | {int(df[f'rf_{ev}_substantive'].sum()):,} | "
            f"{int(df[f'mda_{ev}_substantive'].sum()):,} |")
    add("")
    add("*Reading:* Risk-Factor mentions are overwhelmingly hypothetical "
        "(the substantive share there is the boilerplate test); genuine event "
        "discussion concentrates in MD&A. A mention is SUBSTANTIVE when its "
        "sentence ties the firm to an actual occurrence (past-tense receipt/"
        "action verb, a definite reference such as \"the warning letter\", or "
        "a specific date), not merely a modal risk disclaimer.")
    add("")
    add("> **Caveats.** (1) Only Risk Factors (Item 1A) and MD&A (Item 7 / "
        "Item 2) are parsed; Legal Proceedings (Item 3) also carries actual "
        "recall/letter disclosures and is not captured here. (2) Item 1A was "
        "required only for fiscal years ending on/after 2005-12-01, so "
        "Risk-Factor coverage is thin before 2006. (3) Section boundaries are "
        "located heuristically (widest-span between item headers); a filing "
        "with non-standard headers can yield an empty section, flagged by "
        "`has_risk_factors` / `has_mda`.")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
