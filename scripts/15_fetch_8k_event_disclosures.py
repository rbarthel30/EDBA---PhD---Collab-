# =============================================================
# Script: 15_fetch_8k_event_disclosures.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Build the OUTCOME dataset - SEC Form 8-K disclosures that are
#          specifically ABOUT one of the three FDA regulatory events the panel
#          tracks, with a flag per event type:
#
#              flag_warning_letter   - FDA Warning / Untitled Letter
#              flag_adverse_event    - Medical Device Report (Part 803)
#              flag_recall           - recall / correction & removal (Part 806)
#
#          These are the disclosure responses the paper's hypotheses are
#          about; the gvkey-year-event panel (script 14) is the treatment side.
#
# Sources: 1. EDGAR full-text search (efts.sec.gov) - candidate discovery
#          2. EDGAR Archives - the filing documents themselves
#          API docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
#
# ---------------------------------------------------------------------------
# THE CORE DESIGN PROBLEM: BODY TEXT IS NOISE, THE LEAD IS SIGNAL
#
#   FDA-related 8-Ks routinely mention all three event types even when the
#   filing is about exactly one. The Beta Bionics warning-letter 8-K of
#   2026-01-29 (the reference example) is the canonical case - its Item 8.01
#   opens "the Company received a warning letter ... from the FDA", and then
#   the SAME paragraph goes on to cite non-conformities in "Medical Device
#   Reporting" and "Correction and Removals".
#
#   A naive full-text regex flags that filing as ALL THREE events. It is a
#   warning-letter disclosure and nothing else.
#
#   So classification runs on the LEAD ONLY: the first ~500 characters after
#   each "Item X.XX" heading, where an 8-K states what it is about. Everything
#   before the first Item heading is SEC cover-page boilerplate (registrant
#   address, Rule 425 checkboxes) - roughly the first 2,000 characters, and
#   never substantive - so a "first N characters of the document" rule would
#   capture nothing at all.
#
#   Body matches are still recorded, as `body_mentions_*`, but NEVER drive the
#   flags. Keeping both is what lets the noise cost be measured rather than
#   asserted: compare `flag_*` against `body_mentions_*` to see exactly how
#   many false positives a body-based rule would have introduced.
# ---------------------------------------------------------------------------
#
# SAMPLE: filings whose EDGAR-reported SIC is medical device (3841-3845) or
#   pharma/biologics (2833-2836). EFTS returns SIC on every hit, so the filter
#   needs no Compustat join - though `cik` is carried through so the result
#   joins to the panel on the Compustat CIK.
#
# COVERAGE LIMIT: EDGAR full-text search only indexes 2001 onward. 8-Ks before
#   2001 are NOT discoverable this way and are absent by construction. The
#   modern 8-K item structure dates from the August 2004 amendments, so the
#   usable series effectively starts then.
#
# Outputs: data/raw/edgar_8k_candidates_<DATE>.csv        (EFTS hits, untouched)
#          data/processed/8k_event_disclosures_<DATE>.csv (classified)
#
# Usage:   python scripts/15_fetch_8k_event_disclosures.py
#          python scripts/15_fetch_8k_event_disclosures.py --discover-only
#          python scripts/15_fetch_8k_event_disclosures.py --since 2015
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import os
import re
import sys
import glob
import html
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# SEC requires a declared User-Agent identifying the requester, and throttles
# above 10 requests/second. We stay at ~8/s.
SEC_UA = {"User-Agent": os.environ.get(
    "SEC_USER_AGENT", "University of Miami Research rbarthel15@gmail.com")}
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
REQUEST_SLEEP = 0.13
EFTS_PAGE = 100
EFTS_MAX_FROM = 9_800      # EFTS hard-caps around 10,000 results per query
FIRST_YEAR = 2001          # EDGAR full-text search coverage begins here

DEVICE_SIC = (3841, 3845)
PHARMA_BIO_SIC = (2833, 2836)

# Cache of fetched filing text, DELIBERATELY OUTSIDE THE REPO (OneDrive-synced)
# and separate from classification. Fetching ~8,000 documents takes ~50 minutes
# against SEC's rate limit; classification takes seconds. Coupling them - as the
# first version of this script did - meant every regex revision cost another
# full re-fetch. With the cache, re-classification is instant and SEC is hit
# once. Override with EDGAR_TEXT_CACHE.
_default_cache = (Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
                  / "edba_fda_cache" / "edgar_8k_text")
TEXT_CACHE = Path(os.environ.get("EDGAR_TEXT_CACHE", _default_cache))

# Phrases used ONLY to discover candidates in full-text search. This stage is
# deliberately WIDE (recall-oriented): its job is to avoid missing filings.
# Precision comes later, from the lead-based regex.
DISCOVERY_PHRASES = [
    '"warning letter"', '"untitled letter"',
    '"medical device report"', '"adverse event report"',
    '"voluntary recall"', '"product recall"', '"Class I recall"',
    '"correction and removal"', '"field action"', '"field safety notice"',
    '"recall of certain"', '"initiated a recall"',
]


# =============================================================
# STEP 1. Classification patterns (applied to the LEAD only)
# =============================================================
# Tight, deliberately conservative. Each pattern names the regulatory artefact
# rather than a generic word, so ordinary business language does not trip it.

PAT_WARNING_LETTER = re.compile(
    r"\b(?:fda\s+)?warning\s+letter\b",
    re.I)

# Untitled Letters are tracked SEPARATELY, not folded into the warning-letter
# flag, for two reasons:
#
#   1. They are a different regulatory artefact. A Warning Letter alleges
#      violations serious enough to warrant enforcement; an Untitled Letter is
#      a lower-severity notice, most often about promotional claims. Merging
#      them would blur precisely the severity variation the hypotheses rest on.
#   2. There is NO matching treatment event. Script 03 pulls Warning Letters,
#      Seizures and Injunctions from the FDA Data Dashboard - untitled letters
#      are absent from that data entirely. An 8-K flagged this way therefore
#      has no observable treatment and can never link to the panel.
#
# Kept rather than discarded: they cost nothing now that documents are cached,
# and they are a useful lower-severity comparison group. But `flag_warning_
# letter` must correspond one-to-one with the panel's treatment population.
PAT_UNTITLED_LETTER = re.compile(
    r"\buntitled\s+letter\b",
    re.I)

PAT_ADVERSE_EVENT = re.compile(
    # 'Medical Device Report(ing)' is the Part 803 term of art.
    r"\bmedical\s+device\s+report(?:ing|s)?\b"
    r"|\badverse\s+event\s+report(?:ing|s)?\b"
    r"|\bMDR\s+(?:report|filing|requirement)",
    re.I)

PAT_RECALL = re.compile(
    r"\b(?:voluntar(?:y|ily)|product|initiat\w+|announc\w+)\s+"
    r"(?:a\s+)?recall\b"
    r"|\brecall(?:ed|ing|s)?\s+(?:certain|its|the|all|approximately)\b"
    r"|\bclass\s+(?:I|II|III|1|2|3)\s+recall\b"
    r"|\bcorrections?\s+and\s+removals?\b"
    r"|\bfield\s+(?:safety\s+)?(?:corrective\s+)?action\b"
    r"|\bfield\s+safety\s+notice\b",
    re.I)

# An FDA/device context requirement. 'Warning letter' and 'recall' both occur
# in unrelated commercial settings (a contract warning letter, recalling a
# proxy). Requiring FDA or device context in the document removes those
# without needing the phrase itself to carry it.
PAT_FDA_CONTEXT = re.compile(
    r"\bfda\b|\bfood\s+and\s+drug\s+administration\b"
    r"|\b510\(k\)\b|\bpremarket\b|\bmedical\s+device\b|\bcGMP\b"
    r"|\bquality\s+system\s+regulation\b|\b21\s+CFR\b",
    re.I)

PATTERNS = {
    "warning_letter": PAT_WARNING_LETTER,
    "adverse_event": PAT_ADVERSE_EVENT,
    "recall": PAT_RECALL,
    "untitled_letter": PAT_UNTITLED_LETTER,
}

# The three events that have a counterpart on the treatment side (script 14's
# panel). `untitled_letter` is deliberately excluded: it is collected and
# labelled, but it is not one of the project's three events, so it must not
# silently enter any count of "event disclosures" used against the panel.
PANEL_EVENTS = ["warning_letter", "adverse_event", "recall"]

# ---------------------------------------------------------------------------
# PRODUCT-DOMAIN VOCABULARY - is this event about a DEVICE or a DRUG?
#
# The SIC filter admits pharma/biologics (2833-2836) on purpose: the largest
# device makers - Abbott, J&J, Medtronic - are classified there, so excluding
# those codes would gut the sample. The cost is that pure-pharma firms enter
# too, and a drug-manufacturing warning letter looks identical to a device one
# at the level of the phrase "warning letter".
#
# FDA's own citations disambiguate, because the regulations are domain-
# specific by construction. 21 CFR 820 (Quality System Regulation), 803
# (Medical Device Reporting) and 806 (corrections and removals) apply ONLY to
# devices; 21 CFR 210/211 apply only to drugs. Premarket pathways split the
# same way: 510(k)/PMA/de novo are device, NDA/ANDA are drug, BLA is biologic.
#
# NOTE this makes the recall flag partly self-disambiguating - "corrections
# and removals" is device-only language. The real exposure is warning letters,
# where the artefact itself is domain-neutral.
# ---------------------------------------------------------------------------
PAT_DEVICE_DOMAIN = re.compile(
    r"\b510\(k\)\b|\bpremarket\s+notification\b|\bpremarket\s+approval\b"
    r"|\bPMA\b|\bde\s+novo\b|\bCDRH\b"
    r"|\b21\s*CFR\s*(?:Part\s*)?(?:820|803|806)\b"
    r"|\bquality\s+system\s+regulation\b|\bQSR\b"
    r"|\bmedical\s+device\s+report(?:ing|s)?\b"
    r"|\bcorrections?\s+and\s+removals?\b"
    r"|\bmedical\s+device(?:s)?\b|\bunique\s+device\s+identifi\w+\b"
    r"|\bcatheter\b|\bstent\b|\bimplant(?:able|ed|s)?\b|\bendoscop\w+\b"
    r"|\binfusion\s+pump\b|\bglucose\s+monitor\w*\b|\bdefibrillator\b",
    re.I)

PAT_DRUG_DOMAIN = re.compile(
    r"\bNDA\b|\bANDA\b|\bsNDA\b|\bCDER\b"
    r"|\b21\s*CFR\s*(?:Part\s*)?(?:210|211)\b"
    r"|\bdrug\s+product\b|\bactive\s+pharmaceutical\s+ingredient\b|\bAPI\b"
    r"|\bdrug\s+substance\b|\btablet(?:s)?\b|\bcapsule(?:s)?\b"
    r"|\bsterile\s+inject\w+\b|\boral\s+solution\b|\bvial(?:s)?\b",
    re.I)

PAT_BIOLOGIC_DOMAIN = re.compile(
    r"\bBLA\b|\bCBER\b|\bbiologics?\s+license\b"
    r"|\b21\s*CFR\s*(?:Part\s*)?6\d\d\b"
    r"|\bvaccine(?:s)?\b|\bplasma\s+derived\b|\bcell\s+therapy\b"
    r"|\bgene\s+therapy\b",
    re.I)

DOMAIN_PATTERNS = {
    "device": PAT_DEVICE_DOMAIN,
    "drug": PAT_DRUG_DOMAIN,
    "biologic": PAT_BIOLOGIC_DOMAIN,
}


def classify_domain(text: str, lead: str) -> dict:
    """
    Decide whether the filing concerns a device, a drug, or a biologic.

    Scored on the FULL document rather than the lead: an 8-K commonly opens
    "received a Warning Letter relating to our Irvine facility" and only names
    the product class further down. Requiring domain evidence in the lead
    would discard correct filings on a stylistic technicality - the opposite
    of the lead rule for EVENT type, where the lead is precisely where the
    subject is declared.

    Lead-level scores are reported alongside, so a stricter lead-anchored
    domain rule can be applied later without re-fetching.

    Rows are LABELLED, never dropped: a firm can legitimately disclose a
    device and a drug action in one filing, and the cut belongs to the
    analyst, not the parser.
    """
    out = {}
    scores = {}
    for name, pat in DOMAIN_PATTERNS.items():
        n_doc = len(pat.findall(text))
        out[f"domain_{name}_hits"] = n_doc
        out[f"domain_{name}_lead_hits"] = len(pat.findall(lead))
        scores[name] = n_doc

    top = max(scores, key=scores.get)
    if scores[top] == 0:
        domain = "unspecified"
    else:
        # 'mixed' when a rival domain is within one hit of the leader - these
        # are genuinely combination filings or ambiguous prose, and forcing a
        # winner would fabricate precision.
        rivals = [k for k, v in scores.items()
                  if k != top and v >= scores[top] - 1 and v > 0]
        domain = "mixed" if rivals else top
    out["product_domain"] = domain
    out["is_device_domain"] = domain == "device"
    return out


def in_scope_sic(sic) -> bool:
    """True if an EDGAR-reported SIC is device or pharma/bio."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return False
    return (DEVICE_SIC[0] <= s <= DEVICE_SIC[1]
            or PHARMA_BIO_SIC[0] <= s <= PHARMA_BIO_SIC[1])


def latest(directory: Path, pattern: str):
    """Return the most recent date-stamped file matching a glob, or None."""
    hits = sorted(glob.glob(str(directory / pattern)))
    return Path(hits[-1]) if hits else None


def sec_get(url: str, **kwargs) -> requests.Response:
    """
    GET against SEC with the required User-Agent, throttling, and one retry on
    429. SEC blocks unidentified or over-rate clients outright, so this is the
    only path used for every request in the script.
    """
    for attempt in range(3):
        resp = requests.get(url, headers=SEC_UA, timeout=60, **kwargs)
        if resp.status_code == 429:
            time.sleep(2 + 3 * attempt)     # back off, then retry
            continue
        time.sleep(REQUEST_SLEEP)
        return resp
    return resp


# =============================================================
# STEP 2. Candidate discovery via EDGAR full-text search
# =============================================================
def discover_candidates(since: int) -> pd.DataFrame:
    """
    Find candidate 8-Ks by phrase, PARTITIONED BY YEAR.

    Year partitioning is not cosmetic: EFTS caps a single query at ~10,000
    results, and '"warning letter"' alone returns ~8,900 across all years.
    Any broader phrase, or a future year with more filings, would silently
    truncate. Partitioning keeps every query far below the ceiling, and a
    partition that does approach it is reported.
    """
    rows = []
    this_year = date.today().year
    for phrase in DISCOVERY_PHRASES:
        n_phrase = 0
        for yr in range(max(since, FIRST_YEAR), this_year + 1):
            start = 0
            while True:
                params = {"q": phrase, "forms": "8-K",
                          "startdt": f"{yr}-01-01", "enddt": f"{yr}-12-31",
                          "from": start}
                resp = sec_get(EFTS_URL, params=params)
                if resp.status_code != 200:
                    print(f"      {phrase} {yr}: HTTP {resp.status_code}, skipping")
                    break
                payload = resp.json()
                total = payload.get("hits", {}).get("total", {}).get("value", 0)
                hits = payload.get("hits", {}).get("hits", [])
                if start == 0 and total >= EFTS_MAX_FROM:
                    print(f"      WARNING {phrase} {yr}: {total:,} hits is at "
                          f"the EFTS ceiling - results may be truncated")
                for h in hits:
                    src = h.get("_source", {})
                    sics = src.get("sics") or []
                    ciks = src.get("ciks") or []
                    rows.append({
                        "accession": src.get("adsh"),
                        "document": h.get("_id", "").split(":")[-1],
                        "cik": ciks[0] if ciks else None,
                        "company": (src.get("display_names") or [None])[0],
                        "sic": sics[0] if sics else None,
                        "file_date": src.get("file_date"),
                        "period_ending": src.get("period_ending"),
                        "items": "; ".join(src.get("items") or []),
                        "discovery_phrase": phrase,
                    })
                n_phrase += len(hits)
                start += EFTS_PAGE
                if not hits or start >= min(total, EFTS_MAX_FROM):
                    break
        print(f"    {phrase:26} {n_phrase:,} hits")

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # One filing can match several phrases; keep one row per document and
    # record every phrase that found it.
    df = (df.groupby(["accession", "document"], as_index=False)
            .agg({"cik": "first", "company": "first", "sic": "first",
                  "file_date": "first", "period_ending": "first",
                  "items": "first",
                  "discovery_phrase": lambda s: "; ".join(sorted(set(s)))}))
    return df


# =============================================================
# STEP 3. Fetch and extract text
# =============================================================
def cached_document_text(cik: str, accession: str, document: str,
                         url: str) -> str:
    """
    Return a filing's extracted text, fetching from SEC only on a cache miss.

    Fetching ~8,000 documents costs ~55 minutes against SEC's rate limit;
    re-classifying them costs seconds. Separating the two means a regex change
    no longer implies another hour of network traffic - and it means SEC is
    hit once rather than once per iteration of the classifier.
    """
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{accession}_{document}".replace("/", "_").replace("\\", "_")
    path = TEXT_CACHE / f"{key}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    resp = sec_get(url)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    text = extract_text(decode_filing(resp))
    path.write_text(text, encoding="utf-8", errors="replace")
    return text


def document_url(cik: str, accession: str, document: str) -> str:
    """Build the EDGAR Archives URL for a filing document."""
    cik_int = str(int(cik))
    acc_nodash = accession.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
            f"{acc_nodash}/{document}")


def decode_filing(resp: requests.Response) -> str:
    """
    Decode a filing body as UTF-8.

    SEC serves filings without a charset header, so requests falls back to
    ISO-8859-1 and mangles the typographic quotes EDGAR documents are full of
    ("received a &#8220;Warning Letter&#8221;"). Left uncorrected that can
    split a phrase mid-match, so decoding is forced rather than inferred.
    """
    return resp.content.decode("utf-8", errors="replace")


def extract_text(raw_html: str) -> str:
    """Strip markup and normalize whitespace to a single searchable string."""
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw_html)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    txt = txt.replace("\xa0", " ")
    return re.sub(r"\s+", " ", txt).strip()


def extract_lead(text: str, lead_chars: int = 500) -> tuple:
    """
    Return (lead_text, lead_source).

    The lead is the first `lead_chars` characters following EACH "Item X.XX"
    heading, concatenated. Multi-item 8-Ks are common (an FDA event under Item
    8.01 bundled with Item 9.01 exhibits), so taking only the first item would
    miss filings where the regulatory event is the second item.

    If no Item heading is found - older or malformed filings - fall back to the
    text after the cover-page boilerplate. That fallback is labelled, so its
    rows can be excluded if a referee wants strict item-anchored evidence only.
    """
    items = list(re.finditer(r"item\s+\d+\.\d+", text, re.I))
    if items:
        parts = [text[m.start():m.start() + lead_chars] for m in items]
        return " ".join(parts), "item_anchored"

    # NO ITEM HEADING => this document is an EXHIBIT, not the 8-K form itself.
    # EDGAR full-text search returns the specific FILE that matched, which is
    # very often Exhibit 99.1 (the press release) rather than the parent form:
    # 22 of 25 sampled in-scope candidates had no Item heading at all.
    #
    # For a press release the lead is the HEADLINE AND OPENING PARAGRAPH, i.e.
    # the very top of the document - there is no SEC cover-page boilerplate to
    # skip, because this is not the form. An earlier version skipped to
    # character 1,800 here, which for a press release lands in arbitrary
    # mid-body text: it classified 119 filings on effectively random content
    # and missed any release that announced the event in its headline.
    return text[:lead_chars * 2], "exhibit_top"


def classify(text: str, lead: str) -> dict:
    """
    Apply the event patterns to the LEAD (authoritative) and, separately, to
    the whole document (diagnostic only).

    The FDA-context requirement is checked against the FULL document, not the
    lead: a filing can open "the Company received a Warning Letter" and only
    name the FDA a sentence later. Requiring context in the lead itself would
    reject correct filings for a stylistic reason.
    """
    has_context = bool(PAT_FDA_CONTEXT.search(text))
    out = {"has_fda_context": has_context}
    for name, pat in PATTERNS.items():
        lead_hit = bool(pat.search(lead))
        out[f"flag_{name}"] = bool(lead_hit and has_context)
        out[f"body_mentions_{name}"] = bool(pat.search(text))
    # n_flags counts ONLY the three panel events. An untitled-letter filing has
    # no treatment counterpart, so letting it increment this would inflate any
    # count of disclosures matched against the panel.
    out["n_flags"] = sum(out[f"flag_{n}"] for n in PANEL_EVENTS)
    out["n_flags_incl_untitled"] = sum(out[f"flag_{n}"] for n in PATTERNS)
    out.update(classify_domain(text, lead))
    return out


# =============================================================
# STEP 4. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    since = FIRST_YEAR
    if "--since" in sys.argv:
        since = int(sys.argv[sys.argv.index("--since") + 1])

    cand_path = RAW_DIR / f"edgar_8k_candidates_{snapshot_date}.csv"
    out_path = PROCESSED_DIR / f"8k_event_disclosures_{snapshot_date}.csv"

    print("=" * 64)
    print("SEC 8-K event disclosures - warning letter / MDR / recall")
    print(f"Snapshot date: {snapshot_date} | from {since}")
    print("=" * 64)

    # --- 4a. Discover. ---
    print("[1/4] Discovering candidates via EDGAR full-text search ...")
    if cand_path.exists():
        print(f"    reusing {cand_path.name}")
        cand = pd.read_csv(cand_path, low_memory=False)
    else:
        cand = discover_candidates(since)
        cand.to_csv(cand_path, index=False, encoding="utf-8-sig")
    print(f"    {len(cand):,} distinct candidate filings")

    # --- 4b. SIC filter. ---
    print("[2/4] Filtering to device / pharma-bio SIC ...")
    cand["in_scope"] = cand["sic"].map(in_scope_sic)
    scoped = cand[cand["in_scope"]].copy()
    print(f"    {len(scoped):,} of {len(cand):,} in scope "
          f"({len(scoped) / max(len(cand), 1):.1%}); "
          f"{scoped['cik'].nunique():,} distinct filers")
    if "--discover-only" in sys.argv:
        print("Stopping after discovery (--discover-only).")
        return

    # --- 4c. Fetch + classify. ---
    print(f"[3/4] Fetching and classifying {len(scoped):,} documents "
          f"(~{len(scoped) * REQUEST_SLEEP / 60:.0f} min) ...")
    records, n_fail = [], 0
    for i, row in enumerate(scoped.itertuples(index=False), start=1):
        url = document_url(row.cik, row.accession, row.document)
        try:
            text = cached_document_text(row.cik, row.accession, row.document, url)
            lead, lead_source = extract_lead(text)
            rec = {
                "cik": int(row.cik), "company": row.company, "sic": row.sic,
                "accession": row.accession, "document": row.document,
                "file_date": row.file_date, "period_ending": row.period_ending,
                "items": row.items, "discovery_phrase": row.discovery_phrase,
                "url": url, "lead_source": lead_source,
                "doc_chars": len(text),
            }
            rec.update(classify(text, lead))
            records.append(rec)
        except Exception as exc:  # noqa: BLE001 - one bad doc must not kill the run
            n_fail += 1
            if n_fail <= 5:
                print(f"      fetch failed ({exc}): {url}")
        if i % 250 == 0:
            print(f"    {i:,}/{len(scoped):,} fetched ({n_fail} failures)")

    df = pd.DataFrame(records)
    if df.empty:
        raise RuntimeError("No documents were successfully classified.")

    # Write the FULL classified set alongside the event subset.
    #
    # An earlier version saved only the flagged rows and claimed the exclusion
    # was "reversible via the raw candidate file" - it was not, because that
    # file carries no flags, so there was no way to audit WHY a filing was
    # dropped without re-fetching it. The rejection rule is a sample-
    # construction decision and has to be inspectable.
    all_path = PROCESSED_DIR / f"8k_all_classified_{snapshot_date}.csv"
    df.to_csv(all_path, index=False, encoding="utf-8-sig")
    print(f"    full classified set -> {all_path.relative_to(REPO_ROOT)} "
          f"({len(df):,} rows)")

    # Retain untitled-letter filings too - labelled, not counted as panel
    # events. Filter on `n_flags > 0` downstream for the panel-matched set.
    hits = df[df["n_flags_incl_untitled"] > 0].copy()
    hits.to_csv(out_path, index=False, encoding="utf-8-sig")
    n_panel = int((df["n_flags"] > 0).sum())
    print(f"    fetched {len(df):,} ({n_fail} failures)")
    print(f"    PANEL-EVENT disclosures (WL/AE/recall) : {n_panel:,}")
    print(f"    ... plus untitled-letter only          : "
          f"{len(hits) - n_panel:,}  (labelled, not a panel event)")
    print(f"    processed -> {out_path.relative_to(REPO_ROOT)}")

    # --- 4d. Summary, including the cost of body-based matching. ---
    print("[4/4] Summary")
    for name in PATTERNS:
        lead_n = int(df[f"flag_{name}"].sum())
        body_n = int(df[f"body_mentions_{name}"].sum())
        tag = "" if name in PANEL_EVENTS else "  (not a panel event)"
        print(f"  {name:<16} lead-flagged {lead_n:>5,} | "
              f"body-mentioned {body_n:>5,} | "
              f"body-only FPs avoided: {body_n - lead_n:,}{tag}")

    # Device-domain split - the medical-device subset of each event type.
    if "product_domain" in df.columns:
        print("  product domain (flagged filings):")
        for dom, n in hits["product_domain"].value_counts().items():
            print(f"     {dom:<14} {n:,}")
        print("  device-domain by event type:")
        for name in PANEL_EVENTS:
            sub = hits[hits[f"flag_{name}"] & hits["is_device_domain"]]
            tot = int(hits[f"flag_{name}"].sum())
            print(f"     {name:<16} {len(sub):>4,} of {tot:,} flagged "
                  f"({len(sub) / max(tot, 1):.0%} device)")
    print(f"  filings with >1 flag : {int((hits['n_flags'] > 1).sum()):,}")
    print(f"  lead_source=fallback : "
          f"{int((hits['lead_source'] == 'fallback_offset').sum()):,}")
    if len(hits):
        yrs = pd.to_datetime(hits["file_date"], errors="coerce").dt.year
        print(f"  file_date range      : {int(yrs.min())}-{int(yrs.max())}")
        print(f"  distinct filers      : {hits['cik'].nunique():,}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
