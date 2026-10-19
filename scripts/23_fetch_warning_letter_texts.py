# =============================================================
# Script: 23_fetch_warning_letter_texts.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Download the FULL TEXT of every device warning letter that the
#          project links to a listed (Compustat) firm - the same 206 letters
#          that feed the event panel (script 14) and combined dataset
#          (script 18) - so the letters themselves can be read and coded.
#
# ---------------------------------------------------------------------------
# WHICH LETTERS
#   Device warning letters from the FDA Data Dashboard (script 03), one per
#   unique Case/Injunction ID, linked to a gvkey through the unified crosswalk
#   and ownership windows (script 14's own helpers are imported and REUSED,
#   not copied, so the letter set is identical by construction). The
#   comp.funda "publicly traded that year" test is carried as a FLAG
#   (`publicly_traded_in_letter_year`), as in script 18, not used as a filter.
#
# WHERE THE TEXT COMES FROM (all FDA-published pages)
#   (a) fda.gov, live    - the Warning Letters table lists letters issued
#                          2021+. Each letter URL ends in
#                          -<MARCS-CMS number>-<MMDDYYYY>, and the MARCS-CMS
#                          number IS the dashboard's Case/Injunction ID.
#   (b) Wayback Machine, - letters FDA has since removed from fda.gov. Two URL
#       new scheme         schemes existed. 2014-2020 letters were posted
#                          under the same -<CMS>-<date> slug as (a), so the
#                          Case ID finds them directly in the Internet
#                          Archive's CDX index.
#   (c) Common Crawl,    - letters posted before ~2017 lived at
#       old scheme         /ICECI/EnforcementActions/WarningLetters/<year>/
#       (Wayback as        ucmNNNNNN.htm. The URL carries no Case ID, so FDA's
#        fallback)         own YEAR LISTING PAGES (issue date, company,
#                          issuing office, link) are indexed and each letter
#                          is matched on issue date + recipient name. Both the
#                          listing pages and the letters come from Common
#                          Crawl's 2013-2019 crawls of fda.gov (public WARC
#                          archives built for bulk research access; one crawl
#                          gives a consistent snapshot of a year's
#                          pagination), falling back to the Wayback Machine.
#                          Wayback is NOT the primary source here: it throttles
#                          to a few dozen requests and then blocks the IP for
#                          over an hour (HTTP 429), which made ~500 listing
#                          pages impractical.
#   (c') Letter pages    - FDA's archived index pages are incomplete for some
#        by own title      years (2013, 2015-2016). For letters still missing,
#                          archived letter pages that NO index page lists are
#                          indexed by their own title line ("Medtronic, Inc.
#                          7/17/12") and matched the same way (flagged).
#   FDA's own archive (wayback.archive-it.org/7993) sits behind a bot
#   verification page and is deliberately NOT used.
#
# FORMER NAMES: the dashboard's Legal Name is the establishment's (FEI's)
#   CURRENT name, but old letters went to the firm running it then (a 2008
#   letter to I-Flow shows as "Avanos Medical"). The establishment's earlier
#   names come from FDA's recall records for the same FEI and are also
#   accepted; such letters are flagged ADDRESSED TO FORMER NAME because the
#   9/28 crosswalk may credit them to a later owner (a panel issue).
#
# HOW A DOCUMENT IS CHOSEN AND VERIFIED
#   One MARCS-CMS number can carry several documents (the warning letter, a
#   later close-out letter, a response letter). Every candidate page is
#   fetched and classified from its own text; the chosen document must
#     1. be a WARNING LETTER (not a close-out / response letter), and
#     2. EITHER print the Case ID (CMS #) - a unique identifier, accepted
#        whatever the date gap (flagged if > 7 days) -
#        OR name the recipient firm AND carry a letter date within +/-31
#        days of the dashboard's action date (gaps > 7 days flagged).
#   Old-scheme matches also need the listing's company name to match the
#   dashboard name or a former name of the establishment (exact normalized
#   name, or score >= 90 -> review flag).
#   Every candidate considered is written to an audit file with its scores.
#
# Inputs:  data/processed/fda_compliance_actions_2026-07-06.csv        (script 03)
#          data/processed/fda_firm_gvkey_crosswalk_unified_2026-09-28.csv (script 12, via script 14)
#          data/raw/compustat_funda_2026-09-28.csv                      (flag; gitignored)
#          data/raw/fda_device_recalls_2026-07-19.csv                   (script 10; former
#                                                   establishment names; gitignored)
#          Network: fda.gov, index/data.commoncrawl.org, web.archive.org
#                   (everything cached; see CACHE_DIR)
# Outputs: data/warning_letters/text/<case_id>_<firm>_<date>.txt   (letter text)
#          data/warning_letters/html/<case_id>_<firm>_<date>.html  (page as fetched)
#          data/warning_letters/warning_letter_texts_manifest_<date>.csv
#          data/warning_letters/warning_letter_text_candidates_<date>.csv (audit)
#
# Usage:   python scripts/23_fetch_warning_letter_texts.py
#          (re-runs read the on-disk cache; --refresh re-downloads indexes)
# =============================================================

import argparse
import importlib.util
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

# -------------------------------------------------------------
# STEP 0. Paths and constants
# -------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED = REPO_ROOT / "data" / "processed"
RAW = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "warning_letters"

# Pinned to the 2026-09-28 rebuild so the letter set is exactly the one in
# combined_9_28_26.csv (206 letters, 117 gvkeys).
LETTERS_PATH = PROCESSED / "fda_compliance_actions_2026-07-06.csv"
FUNDA_PATH = RAW / "compustat_funda_2026-09-28.csv"
CROSSWALK_PATH = PROCESSED / "fda_firm_gvkey_crosswalk_unified_2026-09-28.csv"
# openFDA device recalls, raw (script 10; gitignored, regenerable): FEI -> firm
# name at each recall, used for establishments' former names.
RECALLS_RAW_PATH = RAW / "fda_device_recalls_2026-07-19.csv"
EXPECTED_N_LETTERS = 206

# Network caches live OUTSIDE OneDrive, next to the project's other FDA caches.
CACHE_DIR = Path(os.environ["LOCALAPPDATA"]) / "edba_fda_cache" / "warning_letter_text"
PAGE_CACHE = CACHE_DIR / "pages"

FDA = "https://www.fda.gov"
WL_TABLE_PAGE = (FDA + "/inspections-compliance-enforcement-and-criminal-investigations/"
                 "compliance-actions-and-activities/warning-letters")
NEW_SCHEME_PREFIX = "www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/"
OLD_SCHEME_PREFIX = "www.fda.gov/ICECI/EnforcementActions/WarningLetters/"
CDX = "https://web.archive.org/cdx/search/cdx"
# Old-scheme year folders to index. A letter can be posted in the year after
# it is issued, so the folders run one year past the last old-scheme letter.
OLD_SCHEME_YEARS = range(2007, 2018)
YEAR_FOLDER_RE = re.compile(r"/warningletters/(200[7-9]|201[0-7])/", re.I)

CC_INDEX = "https://index.commoncrawl.org"
CC_DATA = "https://data.commoncrawl.org/"
# Common Crawl collections searched for old-scheme pages. FDA retired the
# /ICECI/ URL scheme in its 2017-2019 site migration, so later crawls add
# nothing; CC's first regular crawl is 2013.
CC_CRAWL_YEARS = range(2013, 2020)

HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; rbarthel15@gmail.com)"}
# Seconds between requests, per host. archive.org drew HTTP 429 at 1.5, 4.5
# and 6 s; Common Crawl drew HTTP 429 at 0.5 s on its data server.
DELAYS = {"wayback": 8.0, "fda": 1.0, "cc_index": 1.5, "cc_data": 2.0}
DATE_TOL_DAYS = 31       # max |letter date - dashboard action date|
DATE_FLAG_DAYS = 7       # gaps above this are accepted but review-flagged
FUZZY_MIN = 90           # min name similarity for an old-scheme listing match

CMS_SLUG_RE = re.compile(r"-(\d{5,7})-(\d{8})/?$")
MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
# Full or abbreviated month; CDRH date-stamps read "FEB 12 2010" / "AUG 12, 2010".
DATE_RE = re.compile(rf"\b({MONTHS}|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
                     r"\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b", re.I)
MONTH_NUM = {m[:3].lower(): i for i, m in enumerate(MONTHS.split("|"), 1)}
# Old-site pages also print short numeric dates ("Medtronic, Inc. 7/17/12").
DATE_NUM_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})(?![\d/])")


_S14 = {}


def load_script14():
    """Import script 14 so its sample rules (name normalization, ownership
    windows, funda 'active' test) are reused verbatim."""
    if "mod" not in _S14:
        spec = importlib.util.spec_from_file_location(
            "script14", SCRIPT_DIR / "14_build_gvkey_year_event_panel.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _S14["mod"] = mod
    return _S14["mod"]


def s14_normalize(name):
    """Script 14's firm-name normalization (empty string for blanks)."""
    return load_script14().normalize_name(name) if isinstance(name, str) and name else ""


# -------------------------------------------------------------
# Polite HTTP with retry. archive.org answers bursts with HTTP 429 and keeps
# extending the block if hammered, so a 429 waits minutes, not seconds.
# -------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_last_call = {k: 0.0 for k in DELAYS}
_n429 = {"consecutive": 0}
# --wayback-wait: sit out archive.org blocks (hours). Default: on the first
# 429 stop asking archive.org for the rest of the run and record the
# affected candidates as 'fetch failed'; a later re-run fills them from cache.
WAYBACK = {"wait": False, "blocked": False}


class _Blocked:
    status_code = 429
    content = b""


def http_get(url, kind, params=None, headers=None, tries=8):
    delay = DELAYS[kind]
    if kind == "wayback" and WAYBACK["blocked"]:
        return _Blocked()
    for attempt in range(tries):
        wait = delay - (time.time() - _last_call[kind])
        if wait > 0:
            time.sleep(wait)
        _last_call[kind] = time.time()
        try:
            r = SESSION.get(url, params=params, headers=headers, timeout=90)
        except requests.RequestException as e:
            print(f"      network error ({e.__class__.__name__}); retry {attempt + 1}")
            time.sleep(20)
            continue
        if r.status_code == 429 and kind == "wayback" and not WAYBACK["wait"]:
            WAYBACK["blocked"] = True
            print("      archive.org returned HTTP 429 - no further Wayback requests "
                  "this run (re-run later, or use --wayback-wait)", flush=True)
            return r
        if r.status_code in (429, 503):
            # Back off exponentially. archive.org keeps extending a block that
            # is hit, so it gets 15, 30, 60 ... minutes; Common Crawl's limit
            # clears within minutes, so it gets 1, 2, 4 ... (max 60) minutes.
            base = 60 if kind.startswith("cc") else 900
            pause = min(3600, base * 2 ** _n429["consecutive"])
            _n429["consecutive"] += 1
            print(f"      HTTP 429 (rate limited) - waiting {pause // 60} min", flush=True)
            time.sleep(pause)
            continue
        _n429["consecutive"] = 0
        if r.status_code > 500:
            time.sleep(30)
            continue
        return r
    raise RuntimeError(f"giving up on {url}")


def cached_get(url, kind, cache_name):
    """Fetch once, then serve from PAGE_CACHE (raw bytes kept as fetched)."""
    path = PAGE_CACHE / cache_name
    if path.exists():
        return path.read_bytes(), 200
    r = http_get(url, kind)
    if r.status_code == 200:
        path.write_bytes(r.content)
    return r.content, r.status_code


# -------------------------------------------------------------
# Common Crawl: CDX-style index per crawl, and single WARC records fetched
# by byte range from the public data server.
# -------------------------------------------------------------
def cc_old_scheme_index(refresh) -> pd.DataFrame:
    """Every 200/HTML capture of an /ICECI/.../WarningLetters/ page in the
    2013-2019 crawls, one row per (crawl, URL)."""
    import json
    coll_path = CACHE_DIR / "cc_collinfo.json"
    if not coll_path.exists() or refresh:
        coll_path.write_bytes(http_get(CC_INDEX + "/collinfo.json", "cc_index").content)
    crawls = [c["id"] for c in json.loads(coll_path.read_text())
              if int(c["id"].split("-")[2]) in CC_CRAWL_YEARS]
    recs, skipped = [], []
    for crawl in sorted(crawls):
        path = CACHE_DIR / f"cc_index_{crawl}.jsonl"
        if not path.exists() or refresh:
            api = f"{CC_INDEX}/{crawl}-index"
            # "20*" = the year folders only; it skips /tobacco/, ~3/4 of the prefix.
            q = {"url": OLD_SCHEME_PREFIX + "20*", "output": "json"}
            # The index server times out (HTTP 504) on some older crawls. A
            # crawl that will not load is skipped and NOT cached, so the next
            # run tries it again; the run reports which crawls were skipped.
            try:
                r = http_get(api, "cc_index", params={**q, "showNumPages": "true"}, tries=3)
                if r.status_code == 404:          # no capture under this prefix
                    path.write_text("", encoding="utf-8")
                    continue
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                chunks = []
                for p in range(r.json()["pages"]):
                    rr = http_get(api, "cc_index", params={**q, "page": p}, tries=3)
                    if rr.status_code != 200:
                        raise RuntimeError(f"page {p}: HTTP {rr.status_code}")
                    chunks.append(rr.text)
            except RuntimeError as e:
                print(f"      Common Crawl index {crawl} unavailable ({e}); skipped this run")
                skipped.append(crawl)
                continue
            path.write_text("".join(chunks), encoding="utf-8")
        for line in path.read_text(encoding="utf-8").splitlines():
            # Keep only the 2007-2017 year folders: ~3/4 of captures under the
            # prefix are /WarningLetters/tobacco/ retailer letters.
            if not line.startswith("{") or not YEAR_FOLDER_RE.search(line):
                continue
            # Some URLs carry raw control characters (strict=False tolerates
            # them) or unescaped quotes (unparseable junk URLs: skipped).
            try:
                d = json.loads(line, strict=False)
            except json.JSONDecodeError:
                continue
            if d.get("status") == "200" and "html" in d.get("mime", ""):
                d["crawl"] = crawl
                recs.append(d)
    df = pd.DataFrame(recs)[["crawl", "urlkey", "url", "timestamp", "filename", "offset",
                             "length", "digest"]]
    print(f"    Common Crawl: {len(crawls) - len(skipped)} of {len(crawls)} crawls indexed, "
          f"{len(df):,} old-scheme captures" + (f"; skipped {skipped}" if skipped else ""))
    return df


def cc_fetch(filename, offset, length):
    """One WARC record -> the HTTP body FDA served (bytes), cached."""
    import gzip
    key = f"cc_{Path(filename).stem}_{offset}.html"
    path = PAGE_CACHE / key
    if path.exists():
        return path.read_bytes(), 200
    o, n = int(offset), int(length)
    r = http_get(CC_DATA + filename, "cc_data", headers={"Range": f"bytes={o}-{o + n - 1}"})
    if r.status_code not in (200, 206):
        return b"", r.status_code
    record = gzip.decompress(r.content)
    # WARC headers, blank line, HTTP headers, blank line, body.
    _, http = record.split(b"\r\n\r\n", 1)
    head, body = http.split(b"\r\n\r\n", 1)
    # Common Crawl often stores the payload already decoded while keeping the
    # original (or an X-Crawler-) encoding header, so decode only when the
    # bytes actually are chunked / gzipped.
    head_l = head.lower()
    if re.search(rb"(?m)^transfer-encoding:\s*chunked", head_l):
        try:
            out, rest = b"", body
            while rest:
                size_line, rest = rest.split(b"\r\n", 1)
                size = int(size_line.split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    break
                out, rest = out + rest[:size], rest[size + 2:]
            body = out
        except ValueError:
            pass                                   # not actually chunked
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    path.write_bytes(body)
    return body, 200


# =============================================================
# STEP 1. The letter set: device warning letters linked to a gvkey
# =============================================================
def build_target_letters(s14, extra_ids=()) -> pd.DataFrame:
    """Same rule as script 18's load_warning_letter_events, keeping the
    letter-level identifiers that script drops. `extra_ids` adds letters
    OUTSIDE the 206 (e.g. Armando's US-listing sample, which does not use the
    Compustat link) straight from the dashboard file, with no gvkey and
    in_project_sample = 0."""
    win = s14.load_ownership_windows()
    ca = pd.read_csv(LETTERS_PATH, low_memory=False)
    dev = ca[ca["is_device"] & ca["is_warning_letter"]].copy()
    dev = dev.drop_duplicates("Case/Injunction ID")
    dev["action_date"] = pd.to_datetime(dev["action_taken_date"], errors="coerce")
    dev = dev[dev["action_date"].notna()].copy()
    dev["year"] = dev["action_date"].dt.year.astype(int)
    dev["normalized_name"] = dev["company_name_clean"].map(s14.normalize_name)
    m = dev.merge(win, on="normalized_name", how="inner")
    m = m[(m["year"] >= m["valid_from_year"]) & (m["year"] <= m["valid_to_year"])]
    m = m.drop_duplicates(["gvkey", "Case/Injunction ID"])

    # A letter must map to exactly one listed firm, or the file name and the
    # manifest's gvkey would be ambiguous.
    assert m["Case/Injunction ID"].is_unique, "a letter maps to >1 gvkey"
    assert len(m) == EXPECTED_N_LETTERS, f"expected {EXPECTED_N_LETTERS}, got {len(m)}"

    # Flag (not filter): was the parent publicly traded in the letter year?
    funda = pd.read_csv(FUNDA_PATH, low_memory=False)
    active, _ = s14.build_active_firm_years(funda)
    m["publicly_traded_in_letter_year"] = [
        int((g, y) in active) for g, y in zip(m["gvkey"], m["year"])]
    # funda carries no names; take the Compustat name from the crosswalk.
    cx = pd.read_csv(CROSSWALK_PATH, low_memory=False).dropna(subset=["gvkey", "company_name_compustat"])
    names = cx.assign(gvkey=cx["gvkey"].astype("int64")).groupby("gvkey")["company_name_compustat"].first()
    m["company_name_compustat"] = m["gvkey"].map(names)

    out = pd.DataFrame({
        "case_id": m["Case/Injunction ID"].astype("int64").astype(str),
        "fei_number": m["FEI Number"],
        "recipient_name_fda": m["Legal Name"],
        "recipient_state": m["State"],
        "recipient_country": m["Country/Area"],
        "action_taken_date": m["action_date"].dt.date,
        "letter_year": m["year"],
        "gvkey": m["gvkey"].astype("Int64"),
        "company_name_compustat": m["company_name_compustat"],
        "publicly_traded_in_letter_year": m["publicly_traded_in_letter_year"],
        "in_project_sample": 1,
        "normalized_name": m["normalized_name"],
    })

    extra = [str(i) for i in extra_ids if str(i) not in set(out["case_id"])]
    if extra:
        ex = ca[ca["Case/Injunction ID"].astype("int64").astype(str).isin(extra)]
        ex = ex.drop_duplicates("Case/Injunction ID").copy()
        missing = set(extra) - set(ex["Case/Injunction ID"].astype("int64").astype(str))
        assert not missing, f"case IDs not in the dashboard file: {sorted(missing)}"
        ad = pd.to_datetime(ex["action_taken_date"], errors="coerce")
        out = pd.concat([out, pd.DataFrame({
            "case_id": ex["Case/Injunction ID"].astype("int64").astype(str),
            "fei_number": ex["FEI Number"],
            "recipient_name_fda": ex["Legal Name"],
            "recipient_state": ex["State"],
            "recipient_country": ex["Country/Area"],
            "action_taken_date": ad.dt.date,
            "letter_year": ad.dt.year,
            "gvkey": pd.array([pd.NA] * len(ex), dtype="Int64"),
            "company_name_compustat": None,
            "publicly_traded_in_letter_year": pd.NA,
            "in_project_sample": 0,
            "normalized_name": ex["company_name_clean"].map(s14.normalize_name),
        })], ignore_index=True)
        print(f"    + {len(ex)} letters outside the project sample (requested by case ID)")
    out = out.sort_values(["action_taken_date", "case_id"]).reset_index(drop=True)

    # FORMER NAMES OF THE SAME ESTABLISHMENT. The dashboard's Legal Name is
    # the FEI's CURRENT name, so a 2008 letter to I-Flow shows as "Avanos
    # Medical" and a 2012 letter to McNeil-PPC as "Kenvue". FDA's recall
    # records (script 10's raw openFDA file) give the firm name at each recall
    # for the same FEI; those names are used to find the letter in FDA's
    # old index. A letter found this way is flagged: it may have gone to a
    # different owner than the gvkey the crosswalk assigned.
    rc = pd.read_csv(RECALLS_RAW_PATH, usecols=["firm_fei_number", "recalling_firm"],
                     dtype=str).dropna()
    rc["fei"] = pd.to_numeric(rc["firm_fei_number"], errors="coerce")
    fei_names = (rc.dropna(subset=["fei"])
                 .assign(norm=lambda d: d["recalling_firm"].map(s14.normalize_name))
                 .groupby("fei")["norm"].apply(lambda s: sorted(set(s) - {""})))
    fei = pd.to_numeric(out["fei_number"], errors="coerce")
    out["fei_former_names"] = [
        [n for n in fei_names.get(f, []) if n != own] if pd.notna(f) else []
        for f, own in zip(fei, out["normalized_name"])]
    print(f"    {len(out)} letters, {out['gvkey'].nunique()} firms; "
          f"{int(pd.to_numeric(out['publicly_traded_in_letter_year'], errors='coerce').sum())} "
          f"publicly traded in letter year; "
          f"{sum(map(bool, out['fei_former_names']))} establishments with other names "
          f"in FDA recall records")
    return out


# =============================================================
# STEP 2. Indexes of where letters live
# =============================================================
def fda_live_index(refresh) -> pd.DataFrame:
    """(a) Current fda.gov Warning Letters table via its own DataTables JSON
    endpoint (the xlsx export caps at 1,000 rows and carries no links)."""
    path = CACHE_DIR / "fda_live_index.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype=str)
    params = {"_drupal_ajax": 1, "_wrapper_format": "drupal_ajax",
              "pager_element": 0, "view_args": "",
              "view_base_path": "inspections-compliance-enforcement-and-criminal-investigations/"
                                "compliance-actions-and-activities/warning-letters/datatables-data",
              "view_display_id": "warning_letter_solr_block",
              "view_name": "warning_letter_solr_index",
              "view_path": "/inspections-compliance-enforcement-and-criminal-investigations/"
                           "compliance-actions-and-activities/warning-letters",
              "draw": 1, "length": 500}
    # Same AJAX signature gotcha as the old xlsx export: no header, no data.
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": WL_TABLE_PAGE}
    rows, start, total = [], 0, None
    while total is None or start < total:
        j = http_get(FDA + "/datatables/views/ajax", "fda",
                     params={**params, "start": start}, headers=hdr).json()
        total = j["recordsTotal"]
        if not j["data"]:
            break
        rows += j["data"]
        start += len(j["data"])

    def strip(x):
        return re.sub(r"<[^>]+>", "", x or "").strip()
    df = pd.DataFrame([{
        "posted_date": strip(d[0]), "issue_date": strip(d[1]),
        "company": strip(d[2]),
        "url": (re.search(r'href="([^"]+)"', d[2]) or [None, None])[1],
        "issuing_office": strip(d[3]), "subject": strip(d[4])} for d in rows])
    df["url"] = FDA + df["url"]
    assert len(df) == total, "fda.gov index incomplete"
    df.to_csv(path, index=False)
    return df


def wayback_cdx(prefix, name, refresh) -> pd.DataFrame:
    """One CDX dump per URL prefix: every distinct URL the Archive captured
    with HTTP 200, with the timestamp of a good capture."""
    path = CACHE_DIR / f"cdx_{name}.txt"
    if not path.exists() or refresh:
        r = http_get(CDX, "wayback", params={
            "url": prefix, "matchType": "prefix", "filter": "statuscode:200",
            "collapse": "urlkey", "fl": "original,timestamp"})
        assert r.status_code == 200 and not r.text.lstrip().startswith("<"), "CDX failed"
        path.write_text(r.text, encoding="utf-8")
    return pd.read_csv(path, sep=" ", header=None, names=["url", "timestamp"],
                       dtype=str)


def wayback_url(original, ts):
    # `id_` returns the page exactly as FDA served it (no Archive toolbar).
    return f"https://web.archive.org/web/{ts}id_/{original}"


def parse_listing_page(body, listing_url) -> pd.DataFrame:
    """One archived listing page -> issue date / company / office / subject /
    letter link rows."""
    soup = BeautifulSoup(body, "lxml")
    rows = []
    for tr in soup.find_all("tr"):
        td = tr.find_all("td")
        a = tr.find("a", href=re.compile(r"ucm\d+\.htm", re.I))
        if len(td) < 3 or a is None:
            continue
        # From ~2015 FDA's index appends "[ARCHIVED]" to every company name.
        company = re.sub(r"\s*[\[(]?\s*archived\s*[\])]?\s*$", "", a.get_text(" ", strip=True),
                         flags=re.I)
        rows.append({"issue_date": td[0].get_text(" ", strip=True),
                     "company": company,
                     "issuing_office": td[2].get_text(" ", strip=True),
                     "subject": td[3].get_text(" ", strip=True) if len(td) > 3 else "",
                     "href": a["href"], "listing_url": listing_url})
    df = pd.DataFrame(rows, columns=["issue_date", "company", "issuing_office",
                                     "subject", "href", "listing_url"])
    df["ucm_path"] = (df["href"].str.extract(r"(WarningLetters/\d{4}/ucm\d+\.htm)",
                                             flags=re.I)[0].str.lower())
    df["issue_date_parsed"] = pd.to_datetime(df["issue_date"], errors="coerce")
    df["index_source"] = "FDA index page"
    return df.dropna(subset=["ucm_path", "issue_date_parsed"])


def letter_page_title_index(caps, old_idx, todo, s14, window_only=False) -> pd.DataFrame:
    """
    (c') Index the archived old-scheme LETTER pages that no archived FDA
    index page lists, from each page's own title line - the old site opens
    every letter with "<Company> <m/d/yy>" (e.g. "Medtronic, Inc. 7/17/12").
    Common Crawl copies only (Wayback throttles too hard for ~2,000 pages).
    Rows are marked index_source = 'letter page title'; such matches must
    carry an explicit WARNING LETTER heading and are review-flagged.
    """
    lst = caps[(caps["archive"] == "Common Crawl") & caps["ucm_path"].notna()
               & caps["folder"].isin(list(OLD_SCHEME_YEARS))
               & ~caps["ucm_path"].isin(set(old_idx["ucm_path"]))].copy()
    lst["crawl_order"] = lst["crawl"].rank(method="dense", ascending=False)
    lst = lst.sort_values(["ucm_path", "crawl_order"]).drop_duplicates("ucm_path")

    # PRIORITY. FDA numbered pages (ucmNNNNNN) as it posted them, and letters
    # are usually posted within weeks of issue, so the page numbers of
    # INDEXED letters issued within a few days of a missing letter bound where
    # that letter's page should be (5th-95th percentile). Pages inside any
    # missing letter's window are read first; the rest follow, and reading
    # stops once every missing letter has a title match.
    lst["ucm"] = lst["ucm_path"].str.extract(r"ucm(\d+)")[0].astype(int)
    known = old_idx.assign(ucm=old_idx["ucm_path"].str.extract(r"ucm(\d+)")[0].astype(int))
    todo = todo.assign(ad=pd.to_datetime(todo["action_taken_date"]))
    lst["in_window"] = False
    for t in todo.itertuples():
        for w in (3, 7, 15, 30):
            k = known[(known["issue_date_parsed"] - t.ad).abs().dt.days <= w]
            if len(k) >= 8:
                break
        if len(k):
            lo, hi = k["ucm"].quantile(0.05), k["ucm"].quantile(0.95)
            lst.loc[lst["ucm"].between(lo, hi), "in_window"] = True
    lst = lst.sort_values(["in_window", "ucm"], ascending=[False, True])
    if window_only:
        lst = lst[lst["in_window"]]
    print(f"    {len(lst):,} unlisted letter pages ({lst['in_window'].sum():,} inside the "
          f"missing letters' page-number windows, read first); cached after the first run")
    rows, found = [], set()
    for i, cap in enumerate(lst.to_dict("records"), 1):
        if i % 250 == 0:
            print(f"      {i:,}/{len(lst):,} letter pages; title matches for "
                  f"{len(found)}/{len(todo)} missing letters", flush=True)
        if len(found) == len(todo):
            print(f"      all missing letters have a title match after {i - 1:,} pages")
            break
        body, status = cc_fetch(cap["filename"], cap["offset"], cap["length"])
        if status != 200:
            continue
        text = extract_letter_text(body)
        first = text.splitlines()[0] if text else ""
        m = DATE_NUM_RE.search(first)
        if not m:
            continue                       # untitled page: cannot be indexed
        yy = m[3] if len(m[3]) == 4 else f"20{m[3]}"
        rows.append({"issue_date": m[0], "company": first[:m.start()].strip(" -,"),
                     "issuing_office": "", "subject": "", "href": cap["url"],
                     "listing_url": "(letter page title)", "ucm_path": cap["ucm_path"],
                     "issue_date_parsed": pd.to_datetime(f"{yy}-{m[1]}-{m[2]}",
                                                         errors="coerce"),
                     "index_source": "letter page title"})
        r = rows[-1]
        norm = s14.normalize_name(r["company"])
        for t in todo.itertuples():
            if (pd.notna(r["issue_date_parsed"])
                    and abs((r["issue_date_parsed"] - t.ad).days) <= DATE_TOL_DAYS
                    and best_name(norm, t)[0] >= FUZZY_MIN):
                found.add(t.case_id)
    df = pd.DataFrame(rows).dropna(subset=["issue_date_parsed"])
    df["norm"] = df["company"].map(s14.normalize_name)
    print(f"    {len(df):,} unlisted letter pages indexed by title")
    return df


def best_name(listing_norm, target):
    """Best score of a listing name against the dashboard name and the
    establishment's former names -> (score, name that matched)."""
    names = [target.normalized_name] + list(target.fei_former_names)
    scored = [(name_score(listing_norm, n), n) for n in names]
    return max(scored, key=lambda x: (x[0], x[1] == target.normalized_name))


def name_score(a, b):
    """
    Similarity of two normalized firm names, 0-100 (100 only when equal).
    Word-order differences use token_sort_ratio. A name that CONTAINS the
    other ("BAXTER HEALTHCARE RENAL DIV" vs "BAXTER HEALTHCARE",
    "HAEMOSCOPE DIVISION OF HAEMONETICS" vs "HAEMONETICS") also scores high,
    via token_set_ratio - but only when both names share their first word or
    the shorter is wholly inside the longer, so a shared generic word
    ("MEDICAL") can never carry a match on its own. Capped at 99 so it is
    always review-flagged.
    """
    if a == b:
        return 100
    score = fuzz.token_sort_ratio(a, b)
    ta, tb = a.split(), b.split()
    if ta and tb and (ta[0] == tb[0] or set(ta) <= set(tb) or set(tb) <= set(ta)):
        score = max(score, min(99, fuzz.token_set_ratio(a, b)))
    return score


UCM_RE = r"(WarningLetters/\d{4}/ucm\d+\.htm)"


def old_scheme_captures(cc_old, cdx_old) -> pd.DataFrame:
    """
    One table of every archived old-scheme capture from BOTH archives, with
    what is needed to fetch it: Common Crawl (crawl, WARC file, offset,
    length) or Wayback (timestamp). `archive_rank` puts Common Crawl first.
    """
    cc = cc_old.assign(archive="Common Crawl", archive_rank=0)
    wb = cdx_old.assign(archive="Wayback Machine", archive_rank=1, crawl="", digest=None,
                        filename="", offset="", length="")
    caps = pd.concat([cc, wb], ignore_index=True)
    caps["folder"] = pd.to_numeric(caps["url"].str.extract(r"/WarningLetters/(\d{4})/",
                                                           flags=re.I)[0], errors="coerce")
    caps["ucm_path"] = caps["url"].str.extract(UCM_RE, flags=re.I)[0].str.lower()
    return caps


def fetch_capture(cap):
    """Fetch one archived capture (a dict/Series from old_scheme_captures)."""
    if cap["archive"] == "Common Crawl":
        return cc_fetch(cap["filename"], cap["offset"], cap["length"])
    key = re.sub(r"[^A-Za-z0-9]+", "_", cap["url"].split("fda.gov", 1)[-1])[-150:]
    return cached_get(wayback_url(cap["url"], cap["timestamp"]), "wayback",
                      f"wb_{key}_{cap['timestamp']}.html")


def old_scheme_listing_index(caps, todo, s14) -> pd.DataFrame:
    """
    (c) Index FDA's archived year-listing pages (2007-2017) into issue date /
    company / office / subject / letter-URL rows.

    Read LAZILY, PAGE-MAJOR. Within each year folder every page number is read
    once (Common Crawl before Wayback, newest crawl first, main listing URL
    before its variants) before any page is re-read from another capture:
    no single crawl captured every page, and a closed year's pagination is
    the same in every later crawl. The folder is abandoned once every
    still-unfound letter dated that year or the year before (a December
    letter can be posted in January) has a STRONG listing hit - same name
    (score >= 90) and listing date within 7 days - or once the index is
    saturated (see below). The stop rule only decides how much to READ; it
    does not decide which document is chosen.
    """
    lst = caps[caps["folder"].isin(list(OLD_SCHEME_YEARS)) & caps["ucm_path"].isna()].copy()
    lst["page"] = pd.to_numeric(lst["url"].str.extract(r"Page=(\d+)", flags=re.I)[0],
                                errors="coerce").fillna(1)
    lst["variant"] = lst["url"].str.extract(r"/\d{4}/([^?]*)", flags=re.I)[0].str.lower().map(
        {"default.htm": 0, "": 1, "index.htm": 2}).fillna(3)
    lst["crawl_order"] = lst["crawl"].rank(method="dense", ascending=False).fillna(0)
    # n-th capture of the same page number (0 = best copy) -> page-major order.
    lst = lst.sort_values(["folder", "page", "archive_rank", "crawl_order", "variant", "timestamp"])
    lst["copy_rank"] = lst.groupby(["folder", "page"]).cumcount()
    lst = lst.sort_values(["folder", "copy_rank", "page"])
    # Byte-identical copies (same Common Crawl content digest) add nothing.
    dup = lst["digest"].notna() & lst.duplicated(["folder", "digest"])
    lst = lst[~dup]
    print(f"    {len(lst):,} archived listing captures available "
          f"({(lst['archive_rank'] == 0).sum():,} Common Crawl), read lazily")

    todo = todo.assign(ad=pd.to_datetime(todo["action_taken_date"]))
    strong = set()
    frames, n_read = [], 0
    # Saturation: a folder is also abandoned once SATURATION_READS reads in a
    # row reveal no letter not already seen in it - its index is exhausted,
    # and a letter still missing is not in FDA's listing at all.
    SATURATION_READS = 60
    lst["folder"] = lst["folder"].astype(int)
    for folder, pages in lst.groupby("folder", sort=True):
        need = todo[todo["ad"].dt.year.isin([folder - 1, folder])]
        seen, stale, stop = set(), 0, "listing exhausted"
        for cap in pages.to_dict("records"):
            if set(need["case_id"]) <= strong:
                stop = "all letters found"
                break
            if stale >= SATURATION_READS:
                stop = f"saturated ({SATURATION_READS} reads with no new letter)"
                break
            if cap["archive"] == "Common Crawl":
                body, status = cc_fetch(cap["filename"], cap["offset"], cap["length"])
            else:
                key = ("listing_" + re.sub(r"[^A-Za-z0-9]+", "_",
                                           cap["url"].split("WarningLetters/")[-1])
                       + f"_{cap['timestamp']}.html")
                body, status = cached_get(wayback_url(cap["url"], cap["timestamp"]),
                                          "wayback", key)
            n_read += 1
            if status != 200:
                continue
            page = parse_listing_page(body, cap["url"])
            page["norm"] = page["company"].map(s14.normalize_name)
            frames.append(page)
            new = set(page["ucm_path"]) - seen
            seen |= new
            stale = 0 if new else stale + 1
            for t in need.itertuples():
                close = page[(page["issue_date_parsed"] - t.ad).abs().dt.days <= DATE_FLAG_DAYS]
                if any(best_name(n, t)[0] >= FUZZY_MIN for n in close["norm"]):
                    strong.add(t.case_id)
        print(f"      folder {folder}: {len(seen)} letters indexed; strong hits "
              f"{len(set(need['case_id']) & strong)}/{len(need)} letters dated "
              f"{folder - 1}-{folder}; stop: {stop}; reads so far {n_read}")
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(["ucm_path", "company", "issue_date_parsed"])
    print(f"    {n_read} listing pages read; {df['ucm_path'].nunique()} distinct letters indexed")
    return df


# =============================================================
# STEP 3. Candidate documents per letter
# =============================================================
def candidates_by_case_id(targets, live, cdx_new) -> pd.DataFrame:
    """(a) and (b): any page whose slug carries the Case ID."""
    a = live[["url"]].assign(source="fda.gov (live)", timestamp=None)
    b = cdx_new[["url", "timestamp"]].assign(source="Wayback Machine (fda.gov new URL scheme)")
    b["url"] = b["url"].str.replace(r"^http://", "https://", regex=True).str.rstrip("/")
    allp = pd.concat([a, b], ignore_index=True)
    ext = allp["url"].str.extract(CMS_SLUG_RE)
    allp["case_id"], allp["slug_date"] = ext[0], pd.to_datetime(ext[1], format="%m%d%Y", errors="coerce")
    # Prefer the live page over an archived copy of the same URL.
    allp = allp.dropna(subset=["case_id"]).drop_duplicates("url", keep="first")
    c = targets[["case_id", "action_taken_date"]].merge(allp, on="case_id")
    c["listing_name_score"] = None
    # A slug dated far from the dashboard date is USUALLY a later close-out /
    # response letter under the same MARCS-CMS number - but not always (the
    # slug can carry the posting date), so every page is fetched and judged
    # on its own text; the slug gap is kept for the audit file only.
    c["slug_gap_days"] = (c["slug_date"] - pd.to_datetime(c["action_taken_date"])).dt.days
    return c.drop(columns="action_taken_date")


# Words too common in firm names to identify a firm on their own.
GENERIC_WORDS = set("""MEDICAL HEALTHCARE HEALTH CARE SYSTEMS SYSTEM TECHNOLOGIES TECHNOLOGY
PRODUCTS LABORATORIES LABORATORY INTERNATIONAL USA US AMERICA AMERICAN NORTH GROUP
HOLDINGS MANUFACTURING DEVICES DEVICE SERVICES SERVICE SURGICAL SCIENCES SCIENTIFIC
DIVISION OPERATIONS CENTER DIAGNOSTICS PHARMACEUTICALS PHARMACEUTICAL THE AND OF FOR
LTD LLC GMBH AB AG SA SAS SPA SRL BV NV PLC CO CORP INC COMPANY DBA WORLDWIDE GLOBAL
SOLUTIONS INDUSTRIES ENTERPRISES PUERTO RICO COSTA RICA""".split())


def shared_word(a, b):
    """True if two normalized names share a distinctive word (>= 4 letters,
    not in GENERIC_WORDS): ISOMEDIX, UPPSALA, FRESENIUS."""
    ta = {w for w in a.split() if len(w) >= 4 and w not in GENERIC_WORDS}
    tb = {w for w in b.split() if len(w) >= 4 and w not in GENERIC_WORDS}
    return bool(ta & tb)


def candidates_by_listing(targets, old_idx, caps, requested=False) -> pd.DataFrame:
    """(c): old-scheme listing rows within the date tolerance whose company
    name matches the dashboard recipient. Each candidate letter page carries
    its archived captures in preference order (Common Crawl, latest crawl
    first, then Wayback); fetch_candidate uses the first that loads.

    requested=True (--case-ids, letters a person has already identified by
    case number) adds one looser rule: an index entry dated within 3 days
    that shares a DISTINCTIVE word with the recipient's name or a former name
    ("Steris Isomedix Services" for "Isomedix Operations"). The page must
    still pass the text checks, and the match is flagged."""
    letters = caps.dropna(subset=["ucm_path"]).copy()
    letters["crawl_order"] = letters["crawl"].rank(method="dense", ascending=False).fillna(0)
    letters = letters.sort_values(["ucm_path", "archive_rank", "crawl_order"])
    cap_cols = ["archive", "url", "timestamp", "crawl", "filename", "offset", "length"]
    alts = {k: g[cap_cols].to_dict("records") for k, g in letters.groupby("ucm_path")}
    out = []
    for t in targets.itertuples():
        ad = pd.Timestamp(t.action_taken_date)
        near = old_idx[(old_idx["issue_date_parsed"] - ad).abs().dt.days <= DATE_TOL_DAYS]
        for r in near.itertuples():
            score, via = best_name(r.norm, t)
            rule = "name"
            if (score < FUZZY_MIN and requested
                    and abs((r.issue_date_parsed - ad).days) <= 3
                    and any(shared_word(r.norm, n) for n in
                            [t.normalized_name] + list(t.fei_former_names))):
                score, via, rule = FUZZY_MIN - 1, t.normalized_name, "same-date shared word"
            if score >= FUZZY_MIN or rule != "name":
                out.append({"case_id": t.case_id, "ucm_path": r.ucm_path,
                            "matched_former_name": "" if via == t.normalized_name else via,
                            "listing_company": r.company, "listing_issue_date": r.issue_date_parsed,
                            "index_source": getattr(r, "index_source", "FDA index page"),
                            "listing_name_score": score, "listing_match_rule": rule})
    c = pd.DataFrame(out)
    if c.empty:
        return c
    c = c.drop_duplicates(["case_id", "ucm_path"])
    c["_captures"] = c["ucm_path"].map(lambda p: alts.get(p, []))
    c["url"] = c["_captures"].map(lambda a: a[0]["url"] if a else None)
    c["source"] = "(fda.gov old URL scheme)"      # archive name prefixed at fetch time
    c["slug_date"] = c["listing_issue_date"]
    return c


# =============================================================
# STEP 4. Fetch, extract, classify one candidate page
# =============================================================
def extract_letter_text(html: bytes) -> str:
    """Letter body only: the <article> on the current site, the
    'middle-column' div on the pre-2017 site; navigation, scripts and HTML
    comments are dropped."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav"]):
        tag.decompose()
    node = (soup.find("article") or soup.find("div", class_="middle-column")
            or soup.find(attrs={"role": "main"}) or soup.find("main") or soup.body)
    text = node.get_text("\n") if node else ""
    text = text.replace("\xa0", " ")
    # The old site appends a 'Page Last Updated' footer inside the column.
    text = re.split(r"\n\s*Page Last Updated", text)[0]
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text.strip()


def classify(text: str):
    """
    Document type from the letter BODY, plus every date printed near the top.

    The post-2017 site opens each page with a category label (WARNING LETTER /
    CLOSEOUT LETTER / RESPONSE LETTER) that FDA RE-LABELS when a case closes:
    a page labelled CLOSEOUT LETTER can still hold the original warning
    letter (e.g. Spinal Elements, 2014). So the label is kept for the audit
    file, but the type is read from the body:
      * close-out letter - FDA's close-out formula ("has completed an
        evaluation of your corrective actions");
      * response letter  - the firm's own reply posted by FDA (label);
      * warning letter   - a standalone WARNING LETTER heading below the label.
    """
    lines = text.splitlines()
    label = lines[0].strip().upper() if lines else ""
    has_label = label in {"WARNING LETTER", "CLOSEOUT LETTER", "CLOSE-OUT LETTER",
                          "RESPONSE LETTER"}
    body = "\n".join(lines[1:]) if has_label else text
    top = body[:5000]
    # Wording varies ("completed an evaluation" / "completed evaluation";
    # "your firm's" / OCR'd "your ftrm's"), so allow one free word.
    if re.search(r"has completed (an )?evaluation of (your|the)\s+(\S+\s+)?corrective action",
                 top, re.I):
        doc_type = "close-out letter"
    elif label == "RESPONSE LETTER":
        doc_type = "response letter"
    elif re.search(r"(?m)^\s*WARNING LETTER\b", top, re.I) or label == "WARNING LETTER":
        doc_type = "warning letter"
    else:
        doc_type = "unknown"
    dates = [pd.to_datetime(f"{m[2]}-{MONTH_NUM[m[0][:3].lower()]}-{m[1]}", errors="coerce")
             for m in DATE_RE.findall(text[:3000])]
    dates += [pd.to_datetime(f"{m[0]}/{m[1]}/{m[2]}", errors="coerce",
                             format="%m/%d/%Y" if len(m[2]) == 4 else "%m/%d/%y")
              for m in DATE_NUM_RE.findall(text[:3000])]
    dates = [d for d in dates if pd.notna(d)]
    return doc_type, dates, (label if has_label else "")


def score_candidate(cand, target, fetched):
    body, status = fetched
    row = {"http_status": status}
    if status != 200:
        return {**row, "doc_type": "fetch failed", "accept": False}
    text = extract_letter_text(body)
    doc_type, dates, page_label = classify(text)
    # On the old site the company-name link in FDA's own index IS the warning
    # letter (close-out and response letters sit in separate columns), so a
    # page without a standalone heading is still the letter - unless its body
    # is a close-out.
    # Not for pages found by their own title (no index link vouches for them).
    if (doc_type == "unknown" and cand["source"].endswith("old URL scheme)")
            and cand.get("index_source") != "letter page title"):
        doc_type = "warning letter"
        page_label = "(old-site index link)"
    ad = pd.Timestamp(target.action_taken_date)
    # Closest printed date to the dashboard date (letters also print
    # inspection and response dates, so 'first date' alone can mislead).
    gaps = [abs((d - ad).days) for d in dates]
    gap = min(gaps) if gaps else None
    letter_date = dates[gaps.index(gap)].date() if gaps else None
    id_in_text = bool(re.search(rf"(?<!\d){target.case_id}(?!\d)", text))
    # The recipient is named if the first word of the dashboard name, of the
    # FDA index entry, or of the establishment's matched former name appears
    # as a whole word (letters go to the firm's name AT THE TIME).
    names = [target.normalized_name, cand.get("matched_former_name") or "",
             s14_normalize(cand.get("listing_company") or "")]
    toks = {n.split()[0] for n in names if isinstance(n, str) and n.split()}
    clean = " " + re.sub(r"[^A-Z0-9 ]", " ", text.upper()) + " "
    name_in_text = any(f" {tok} " in clean for tok in toks)
    # The MARCS-CMS number is a unique identifier: a warning letter printing
    # the Case ID is accepted whatever the date gap (the dashboard sometimes
    # carries a later date, e.g. Ocular Therapeutix: close-out date 2020 for
    # a 2018 letter); the gap is review-flagged. Without the ID, the letter
    # must name the recipient AND be dated within the tolerance.
    accept = (doc_type == "warning letter" and len(text) > 1500
              and (id_in_text or (name_in_text and gap is not None
                                  and gap <= DATE_TOL_DAYS)))
    return {**row, "doc_type": doc_type, "page_label": page_label,
            "letter_date_in_text": letter_date,
            "date_gap_days": gap, "case_id_in_text": id_in_text,
            "name_in_text": name_in_text, "text_chars": len(text),
            "accept": accept, "_text": text, "_html": body}


def fetch_candidate(c):
    """Fetch a candidate page. Old-scheme candidates try their archived
    captures in order and record (in `c`, in place) which one was used."""
    if c["source"] == "fda.gov (live)":
        cache = "live_" + c["url"].rsplit("/", 1)[-1] + ".html"
        return cached_get(c["url"], "fda", cache)
    if "_captures" in c and isinstance(c["_captures"], list):
        caps, c["_captures"] = c["_captures"], None
        last = (b"", 404)
        for cap in caps:
            last = fetch_capture(cap)
            if last[1] == 200:
                c.update({k: cap[k] for k in ("url", "timestamp", "crawl", "filename",
                                              "offset", "length")})
                c["source"] = f"{cap['archive']} (fda.gov old URL scheme)"
                return last
        c["source"] = "(fda.gov old URL scheme) - no capture loaded"
        return last
    return fetch_capture({**c, "archive": "Wayback Machine"})


def recipient_on_letter(b):
    """The recipient as FDA published it: the name line under the category
    label on the post-2017 site, or FDA's index entry / the page's title line
    (date removed) on the old site."""
    if isinstance(b.get("listing_company"), str) and b["listing_company"]:
        return b["listing_company"]
    lines = [ln.strip() for ln in str(b.get("_text", "")).splitlines() if ln.strip()]
    if lines and lines[0].upper() in {"WARNING LETTER", "CLOSEOUT LETTER",
                                      "CLOSE-OUT LETTER", "RESPONSE LETTER"}:
        return lines[1] if len(lines) > 1 else ""
    if lines:
        m = DATE_NUM_RE.search(lines[0])
        return lines[0][:m.start()].strip(" -,") if m else ""
    return ""


def archive_locator(b):
    """Human-usable pointer to the exact archived copy used."""
    src = str(b.get("source", ""))
    if src.startswith("Common Crawl"):
        return f"{b['crawl']} {b['filename']} offset={b['offset']} length={b['length']}"
    if src.startswith("Wayback"):
        return f"https://web.archive.org/web/{b['timestamp']}/{b['url']}"
    return ""


# =============================================================
# STEP 5. Choose one document per letter and write the outputs
# =============================================================
def slugify(s, n=40):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:n].strip("-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the fda.gov, Wayback CDX and Common Crawl indexes")
    ap.add_argument("--wayback-wait", action="store_true",
                    help="sit out archive.org HTTP 429 blocks (can take hours) "
                         "instead of skipping Wayback for the rest of the run")
    ap.add_argument("--case-ids", default="",
                    help="comma/space-separated FDA case IDs: search ONLY these and "
                         "merge the results into the latest manifest (IDs outside "
                         "the 206 are added with in_project_sample = 0)")
    ap.add_argument("--title-window-only", action="store_true",
                    help="step 4b: read only unlisted pages inside the missing letters' "
                         "page-number windows (much faster; pages outside rarely match)")
    args = ap.parse_args()
    WAYBACK["wait"] = args.wayback_wait
    only = [x for x in re.split(r"[,\s]+", args.case_ids) if x]
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "text").mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "html").mkdir(parents=True, exist_ok=True)
    s14 = load_script14()

    print("[1/5] Letter set (device warning letters linked to a gvkey) ...")
    targets = build_target_letters(s14, extra_ids=only)
    if only:
        targets = targets[targets["case_id"].isin(only)].reset_index(drop=True)
        print(f"    --case-ids: searching only these {len(targets)} letters")

    print("[2/5] Indexes: fda.gov live table, Wayback CDX, Common Crawl index ...")
    live = fda_live_index(args.refresh)
    print(f"    fda.gov live table: {len(live):,} letters")
    cdx_new = wayback_cdx(NEW_SCHEME_PREFIX, "new_scheme", args.refresh)
    cdx_old = wayback_cdx(OLD_SCHEME_PREFIX, "old_scheme", args.refresh)
    print(f"    Wayback CDX: {len(cdx_new):,} new-scheme, {len(cdx_old):,} old-scheme URLs")
    caps = old_scheme_captures(cc_old_scheme_index(args.refresh), cdx_old)

    print("[3/5] Candidates by Case ID (fda.gov live + Wayback new scheme) ...")
    cand = candidates_by_case_id(targets, live, cdx_new)
    tmap = targets.set_index("case_id")
    results = []

    def run(cands):
        for c in cands.to_dict("records"):
            t = tmap.loc[c["case_id"]].copy()
            t["case_id"] = c["case_id"]
            res = score_candidate(c, t, fetch_candidate(c))
            results.append({**c, **res})

    run(cand)
    done = {r["case_id"] for r in results if r["accept"]}
    print(f"    accepted so far: {len(done)} of {len(targets)}")

    print("[4/5] Remaining letters: old-scheme listing match (Common Crawl, then Wayback) ...")
    todo = targets[~targets["case_id"].isin(done)]
    old_idx = old_scheme_listing_index(caps, todo, s14)
    lc = candidates_by_listing(todo, old_idx, caps, requested=bool(only))
    if not lc.empty:
        miss_cap = lc["_captures"].map(len).eq(0)
        if miss_cap.any():
            print(f"    {miss_cap.sum()} listing hits have no archived letter page")
        run(lc[~miss_cap])

    # 4b. FDA's archived index pages are incomplete for some years (2013 and
    # 2015-2016 above all), so letters still missing are looked for among the
    # archived letter pages that no index page lists, by their own titles.
    done = {r["case_id"] for r in results if r["accept"]}
    todo2 = targets[~targets["case_id"].isin(done)
                    & (pd.to_datetime(targets["action_taken_date"]).dt.year
                       <= max(OLD_SCHEME_YEARS))]
    print(f"[4b/5] {len(todo2)} pre-2018 letters still missing: indexing unlisted "
          f"letter pages by their own titles (Common Crawl) ...")
    if len(todo2):
        title_idx = letter_page_title_index(caps, old_idx, todo2, s14,
                                            window_only=args.title_window_only)
        lc2 = candidates_by_listing(todo2, title_idx, caps, requested=bool(only))
        if not lc2.empty:
            run(lc2[lc2["_captures"].map(len).gt(0)])
    res = pd.DataFrame(results)

    print("[5/5] Choosing one document per letter; writing outputs ...")
    acc = res[res["accept"]].copy()
    # Rank: printed Case ID beats name-only; then closest date; exact listing
    # name beats fuzzy; live page beats archive.
    acc["_r_id"] = ~acc["case_id_in_text"].astype(bool)
    acc["_r_src"] = acc["source"].ne("fda.gov (live)")
    acc["_r_name"] = -pd.to_numeric(acc["listing_name_score"], errors="coerce").fillna(100)
    acc = acc.sort_values(["case_id", "_r_id", "date_gap_days", "_r_name", "_r_src"])
    n_tied = acc.groupby("case_id").size()
    best = acc.drop_duplicates("case_id").set_index("case_id")

    stamp = date.today().isoformat()
    rows = []
    for t in targets.itertuples():
        base = {k: getattr(t, k) for k in targets.columns
                if k not in ("normalized_name", "fei_former_names")}
        base["fei_former_names"] = "; ".join(t.fei_former_names)
        if t.case_id not in best.index:
            rows.append({**base, "text_found": 0, "review_flag": "NOT FOUND"})
            continue
        b = best.loc[t.case_id]
        stem = f"{t.case_id}_{slugify(t.recipient_name_fda)}_{t.action_taken_date}"
        (OUT_DIR / "text" / f"{stem}.txt").write_text(b["_text"] + "\n", encoding="utf-8")
        (OUT_DIR / "html" / f"{stem}.html").write_bytes(b["_html"])
        flags = []
        if b["date_gap_days"] > DATE_FLAG_DAYS:
            flags.append(f"letter date {b['date_gap_days']}d from dashboard date")
        if not b["case_id_in_text"]:
            flags.append("case ID not printed; matched on date+name")
        score = pd.to_numeric(b["listing_name_score"], errors="coerce")
        if b.get("listing_match_rule") == "same-date shared word":
            flags.append(f"matched FDA index entry '{b['listing_company']}' on date + a "
                         f"shared distinctive word (requested case ID)")
        elif pd.notna(score) and score < 100:
            flags.append(f"fuzzy listing name match ({score:.0f}): {b['listing_company']}")
        if n_tied[t.case_id] > 1 and not b["case_id_in_text"]:
            flags.append(f"{n_tied[t.case_id]} acceptable pages; closest chosen")
        if b.get("index_source") == "letter page title":
            flags.append("not in FDA's archived index pages; found by the letter "
                         "page's own title")
        former = b.get("matched_former_name")
        recipient = recipient_on_letter(b)
        if isinstance(former, str) and former:
            flags.append(f"ADDRESSED TO FORMER NAME '{recipient}' of this "
                         f"establishment (FDA recall records) - check gvkey attribution "
                         f"for {t.letter_year}")
        elif recipient and best_name(s14_normalize(recipient), t)[0] < FUZZY_MIN:
            # Any route (incl. Case ID): the letter itself names another firm
            # than the dashboard's current name (e.g. a 2021 letter to Smiths
            # Medical shown as ICU Medical, which bought Smiths in 2022).
            flags.append(f"ADDRESSED TO '{recipient}', not the dashboard name - check "
                         f"gvkey attribution for {t.letter_year}")
        rows.append({**base, "text_found": 1, "source": b["source"],
                     "source_url": b["url"],
                     "archive_capture": archive_locator(b),
                     "letter_date_in_text": b["letter_date_in_text"],
                     "date_gap_days": b["date_gap_days"],
                     "case_id_in_text": int(b["case_id_in_text"]),
                     "listing_company": b.get("listing_company", ""),
                     "matched_former_name": former if isinstance(former, str) else "",
                     "recipient_on_letter": recipient,
                     "text_chars": b["text_chars"],
                     "text_file": f"text/{stem}.txt", "html_file": f"html/{stem}.html",
                     "review_flag": "; ".join(flags)})
    man = pd.DataFrame(rows)
    audit = res.drop(columns=[c for c in res.columns if c.startswith("_")])
    old_man = sorted(OUT_DIR.glob("warning_letter_texts_manifest_*.csv"))
    old_aud = sorted(OUT_DIR.glob("warning_letter_text_candidates_*.csv"))
    if only and old_man:
        # Targeted run: keep every other letter from the latest manifest (and
        # audit) and replace only the rows for the requested case IDs.
        prev = pd.read_csv(old_man[-1], dtype=str)
        prev = prev[~prev["case_id"].isin(man["case_id"])]
        # Manifests written before --case-ids existed hold only the 206.
        if "in_project_sample" not in prev.columns:
            prev["in_project_sample"] = "1"
        prev["in_project_sample"] = prev["in_project_sample"].fillna("1")
        man = pd.concat([prev, man.astype(str).replace({"nan": "", "<NA>": "", "None": ""})],
                        ignore_index=True)
        man["text_found"] = pd.to_numeric(man["text_found"]).astype(int)
        man = man.sort_values(["action_taken_date", "case_id"]).reset_index(drop=True)
        if old_aud:
            pa = pd.read_csv(old_aud[-1], dtype=str)
            audit = pd.concat([pa[~pa["case_id"].isin(set(targets["case_id"]))], audit],
                              ignore_index=True)
    # Remove letter files left by earlier runs that this run did not write
    # (e.g. a letter whose chosen document changed), so the folders always
    # match the manifest exactly.
    keep = set(man["text_file"].dropna()) | set(man["html_file"].dropna())
    for sub in ("text", "html"):
        for f in (OUT_DIR / sub).iterdir():
            if f"{sub}/{f.name}" not in keep:
                f.unlink()
    # Two letters should never share one document; if they do (e.g. one
    # letter carried under two Case IDs), flag both rather than hide it.
    url = man["source_url"].replace("", pd.NA)
    shared = url.notna() & url.duplicated(keep=False)
    add = shared & ~man["review_flag"].fillna("").str.contains("SAME PAGE AS ANOTHER LETTER")
    if add.any():
        man.loc[add, "review_flag"] = (man.loc[add, "review_flag"].fillna("")
                                       + "; SAME PAGE AS ANOTHER LETTER").str.lstrip("; ")
    print(f"    letters sharing a page with another letter: {int(shared.sum())}")
    man.to_csv(OUT_DIR / f"warning_letter_texts_manifest_{stamp}.csv", index=False)
    audit.to_csv(OUT_DIR / f"warning_letter_text_candidates_{stamp}.csv", index=False)
    # One manifest/audit in the folder: older dated copies are superseded.
    for f in old_man + old_aud:
        if stamp not in f.name:
            f.unlink()

    found = man["text_found"].sum()
    print(f"    letters with text: {found} of {len(man)}")
    print(man.groupby("letter_year")["text_found"].agg(["sum", "count"]).T.to_string())
    print(f"    by source:\n{man['source'].value_counts().to_string()}")
    print(f"    review-flagged: {(man['review_flag'].fillna('') != '').sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
