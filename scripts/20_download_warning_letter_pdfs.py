# =============================================================
# Script: 20_download_warning_letter_pdfs.py
# Author: Armando Cuello (built with Claude Code)
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Save a PDF copy of every FDA device warning letter that went to a
#          publicly traded company or its subsidiary (status "Yes" or "Yes - via
#          parent" in script 19's output, including the excluded LASIK-clinic
#          letters so that exclusion can be checked). One PDF per distinct letter
#          (FDA case number); a letter covering several facilities is saved once.
# Inputs:  data/processed/warning_letters_us_listing_status_<date>.xlsx (script 19, latest)
# Outputs: data/raw/fda_warning_letter_pdfs/<letter date>_<company>_<case #>.pdf   (gitignored)
#          data/processed/warning_letter_pdf_log_<YYYY-MM-DD>.xlsx  (one row per letter: found or not, how, URL, file)
#
# WHERE THE LETTERS ARE FOUND (in this order)
#   1. fda.gov warning-letter search (live site, letters ~2021 onward). Page
#      addresses end in "-<case #>-<MMDDYYYY>", so the match is exact by case #.
#   2. Internet Archive (web.archive.org) copies of fda.gov pages with that same
#      address format - FDA migrated letters dated ~2014 onward to it. Exact by case #.
#   3. Internet Archive copies of FDA's old yearly warning-letter lists
#      (fda.gov/ICECI/EnforcementActions/WarningLetters/<year>/), used for older
#      letters that have no case # in their address: matched by company name
#      (fuzzy) and letter date (within 15 days).
#   Letters FDA never posted, or pages the archive never saved, are logged as
#   "not found".
#
# PDFs are made by printing the web page with headless Google Chrome; each PDF is
# checked to contain letter text ("Dear" / "WARNING LETTER") before it is kept.
# Re-running skips letters whose PDF already exists.
# =============================================================
import glob
import html
import json
import re
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from pypdf import PdfReader
from rapidfuzz import fuzz

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
PDF_DIR = RAW_DIR / "fda_warning_letter_pdfs"
CACHE = RAW_DIR / "fda_warning_letter_index_cache"
CHROME = next(iter(glob.glob("/Applications/Google Chrome*.app/Contents/MacOS/Google Chrome")), None)

UA = {"User-Agent": "Mozilla/5.0 (academic research; rbarthel15@gmail.com)"}
FDA_LIST = ("https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
            "compliance-actions-and-activities/warning-letters")
NEW_PREFIX = "www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/"
CASE_IN_URL = re.compile(r"-(\d{5,7})-(\d{8})/?$")


def page_date(url):
    return datetime.strptime(CASE_IN_URL.search(url).group(2), "%m%d%Y")


def nearest(urls, when):
    """
    A case # can have several pages: the warning letter and later close-out / follow-up letters.
    Take the page dated closest to the warning-letter date.
    """
    return min(urls, key=lambda u: abs((page_date(u) - when).days)) if urls else None


def get(url, tries=6, pause=4, **kw):
    for i in range(tries):
        try:
            r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=120, **kw)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(pause * (i + 1))
    return None


# -------------------------------------------------------------
# Indexes of letter pages
# -------------------------------------------------------------
def live_index():
    """Every letter on fda.gov's current warning-letter search: {case #: url}."""
    path = CACHE / "live_index.json"
    if not path.exists():
        rows, start = [], 0
        while True:
            r = get("https://www.fda.gov/datatables/views/ajax",
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": FDA_LIST},
                    params=dict(draw=1, start=start, length=500, view_name="warning_letter_solr_index",
                                view_display_id="warning_letter_solr_block"))
            data = r.json()["data"]
            rows += [m.group(1) for x in data if (m := re.search(r'href="([^"]+)"', x[2]))]
            if len(data) < 500:
                break
            start += 500
            time.sleep(1)
        path.write_text(json.dumps(rows))
    out = {}
    for href in json.loads(path.read_text()):
        if m := CASE_IN_URL.search(href):
            out.setdefault(int(m.group(1)), []).append("https://www.fda.gov" + href)
    return out


def archive_new_index():
    """Internet Archive captures of fda.gov letter pages in the case-# address format: {case #: url}."""
    path = CACHE / "archive_new_index.txt"
    if not path.exists():
        r = get("https://web.archive.org/cdx/search/cdx",
                params=dict(url=NEW_PREFIX, matchType="prefix", fl="original",
                            filter="statuscode:200", collapse="urlkey"))
        path.write_text(r.text)
    out = {}
    for line in path.read_text().split():
        if m := CASE_IN_URL.search(line):
            u = line.replace("http://", "https://").rstrip("/")
            if u not in out.setdefault(int(m.group(1)), []):
                out[int(m.group(1))].append(u)
    return out


ROW = re.compile(r'<tr>\s*<td[^>]*>\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*</td>\s*<td[^>]*>\s*<a href="([^"]+)">'
                 r'(.*?)</a>\s*</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', re.S)


def archive_year_list(y):
    """
    FDA's old yearly warning-letter list for year y, rebuilt from EVERY page of it the Internet
    Archive captured (all ?Page= numbers and sort orders), because any single snapshot misses rows.
    """
    path = CACHE / f"archive_list_{y}_full.json"
    if path.exists():
        return json.loads(path.read_text())
    cdx = get("https://web.archive.org/cdx/search/cdx",
              params=dict(url=f"www.fda.gov/ICECI/EnforcementActions/WarningLetters/{y}/default.htm",
                          matchType="prefix", fl="original,timestamp", filter="statuscode:200"))
    latest = {}
    for line in (cdx.text if cdx else "").splitlines():
        orig, ts = line.rsplit(" ", 1)
        key = orig.replace("https://", "http://")
        latest[key] = max(latest.get(key, ""), ts)
    rows = {}
    old = CACHE / f"archive_list_{y}.json"                 # first-pass list, if any
    if old.exists():
        rows.update({r["url"]: r for r in json.loads(old.read_text())})
    for i, (orig, ts) in enumerate(sorted(latest.items())):
        r = get(f"https://web.archive.org/web/{ts}id_/{orig}", tries=3)
        for issued, href, company, office, subject in ROW.findall(r.text if r else ""):
            url = "https://www.fda.gov" + href if href.startswith("/") else href
            rows[url] = dict(issued=issued, url=url, company=html.unescape(re.sub("<[^>]+>", "", company)).strip(),
                             office=re.sub(r"\s+", " ", re.sub("<[^>]+>", "", office)).strip(),
                             subject=re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", subject))).strip())
        time.sleep(1)
    rows = list(rows.values())
    path.write_text(json.dumps(rows))
    print(f"  archived {y} list: {len(rows)} letters from {len(latest)} captured page versions", flush=True)
    return rows


def name_key(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper().replace("&", " AND "))
    s = re.sub(r"\b(INC|INCORPORATED|LLC|LP|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|GMBH|AG|SA|BV|AB|"
               r"THE|DBA|D B A)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def archived_page(url):
    """Raw archived copy of a letter page (cached), or ''."""
    f = CACHE / "pages" / (re.sub(r"[^A-Za-z0-9]+", "_", url.split("fda.gov")[-1]) + ".html")
    if f.exists():
        return f.read_text(encoding="utf-8")
    for ts in ["2020", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010"]:
        r = get(f"https://web.archive.org/web/{ts}id_/{url}", tries=3)
        if r is not None and re.search(r"Dear|WARNING LETTER", r.text):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(r.text, encoding="utf-8")
            time.sleep(2)
            return r.text
    return ""


US_STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
             "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
             "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
             "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
             "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
             "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
             "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
             "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
             "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
             "Wisconsin": "WI", "Wyoming": "WY", "Puerto Rico": "PR"}


def page_id(url):
    """The same letter can be listed under two addresses (with/without the year folder): key on 'ucmNNN'."""
    m = re.search(r"ucm\d+", url)
    return m.group(0) if m else url


def names_place(text, letter):
    """Does the letter page mention the facility's state (full name or ', XX 12345' form) or country?"""
    st, co = letter["state"], letter["country"]
    if st in US_STATES and (re.search(rf"\b{st}\b", text, re.I) or re.search(rf"\b{US_STATES[st]}\b\.?\s+\d{{5}}", text)):
        return True
    aliases = {"United Kingdom": ["United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", " UK"],
               "South Korea": ["Korea"], "China": ["China", "P.R.C"]}
    return co not in ("United States", "-", "nan") and any(a.lower() in text.lower() for a in aliases.get(co, [co]))


def candidates_old(letter, lists):
    """Entries in the archived yearly lists that match an older letter by name (fuzzy) and date (<=15 days)."""
    out = []
    for y in {letter["date"].year - 1, letter["date"].year, letter["date"].year + 1}:
        for r in lists.get(y, []):
            gap = abs((datetime.strptime(r["issued"], "%B %d, %Y") - letter["date"]).days)
            if gap <= 15:
                score = max(fuzz.token_set_ratio(name_key(n), name_key(r["company"])) for n in letter["names"]) - gap
                if score >= 80:
                    out.append((score, r))
    seen, uniq = set(), []
    for _, r in sorted(out, key=lambda x: -x[0]):
        if page_id(r["url"]) not in seen:
            seen.add(page_id(r["url"]))
            uniq.append(r)
    return uniq


def assign_old(letters, lists):
    """
    One archived page per letter. When several same-day letters share a company name (e.g. the
    Oct-2009 LASIK clinic letters), open each candidate page and keep the one naming the
    facility's state (or country) from the FDA file.
    """
    used, chosen = set(), {}
    for l in letters:
        cands = [r for r in candidates_old(l, lists) if page_id(r["url"]) not in used]
        if not cands:
            continue
        pick = cands[0]
        # more than one possible page, or the name match is only partial: confirm by the facility's location
        if len(cands) > 1 or max(fuzz.ratio(name_key(n), name_key(pick["company"])) for n in l["names"]) < 90:
            hits = [r for r in cands if names_place(archived_page(r["url"]), l)]
            pick = hits[0] if hits else None
        if pick:
            used.add(page_id(pick["url"]))
            chosen[l["case"]] = pick
    return chosen


# -------------------------------------------------------------
# Saving a page as a checked PDF
# -------------------------------------------------------------
def print_pdf(source, out):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=15000", f"--print-to-pdf={out}", source],
                   capture_output=True, timeout=180)
    if not out.exists():
        return 0
    try:
        reader = PdfReader(str(out))
        text = " ".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        text, reader = "", None
    if not re.search(r"Dear|WARNING LETTER|Warning Letter", text) or "can’t be reached" in text \
            or "can't be reached" in text:
        out.unlink()
        return 0
    return len(reader.pages)


def save_letter(url, out, via_archive):
    """Live page: print directly. Archived page: download the raw snapshot, then print the local copy."""
    if not via_archive:
        return print_pdf(url, out)
    text = archived_page(url)
    if not text:
        return 0
    tmp = CACHE / "page.html"
    tmp.write_text(text, encoding="utf-8")
    return print_pdf(tmp.resolve().as_uri(), out)


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s)).strip("-")[:40]


def main():
    today = date.today().isoformat()
    CACHE.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    src = sorted(glob.glob(str(PROCESSED_DIR / "warning_letters_us_listing_status_*.xlsx")))[-1]
    d = pd.read_excel(src, sheet_name="Letters with listing status")
    d = d[d.us_listed_at_letter.str.startswith("Yes")]
    letters = [dict(case=int(c), date=g["Action Taken Date"].min(), names=sorted(set(g["Legal Name"])),
                    listed=" | ".join(sorted(set(g.listed_entity.dropna()))),
                    state=str(g["State"].iloc[0]), country=str(g["Country/Area"].iloc[0]))
               for c, g in d.groupby("Case/Injunction ID")]
    print(f"  {len(letters)} distinct letters to find (from {Path(src).name})")

    live, arch_new = live_index(), archive_new_index()
    old_years = sorted({l["date"].year for l in letters if l["case"] not in live and l["case"] not in arch_new})
    lists = {y: archive_year_list(y) for y in sorted({y + k for y in old_years for k in (-1, 0, 1)}) if y <= 2019}
    old = assign_old([l for l in sorted(letters, key=lambda x: x["date"])
                      if l["case"] not in live and l["case"] not in arch_new], lists)

    log = []
    for i, l in enumerate(sorted(letters, key=lambda x: x["date"])):
        name = slug(l["names"][0])
        out = PDF_DIR / f"{l['date']:%Y-%m-%d}_{name}_{l['case']}.pdf"
        row = dict(case_id=l["case"], letter_date=l["date"].date(), recipient_names=" | ".join(l["names"]),
                   listed_company=l["listed"], found="", method="", url="", pdf_file="", pages=None, fda_subject="", note="")
        if l["case"] in live:
            row.update(method="fda.gov live site (exact case #)", url=nearest(live[l["case"]], l["date"]))
            archived = False
        elif l["case"] in arch_new:
            row.update(method="Internet Archive, case-# address (exact case #)", url=nearest(arch_new[l["case"]], l["date"]))
            archived = True
        elif m := old.get(l["case"]):
            row.update(method=f"Internet Archive, FDA {m['issued'][-4:]} letter list (name + date: "
                              f"'{m['company']}', {m['issued']})", url=m["url"], fda_subject=m["subject"])
            archived = True
        else:
            row.update(found="No", method="not in fda.gov or the Internet Archive lists (not posted, or page not saved)")
            log.append(row)
            continue
        pages = out.exists() and len(PdfReader(str(out)).pages) or save_letter(row["url"], out, archived)
        row.update(found="Yes" if pages else "No", pages=pages or None, pdf_file=out.name if pages else "")
        if pages:
            head = " ".join(p.extract_text() or "" for p in PdfReader(str(out)).pages[:2])
            if re.search(r"CLOSE-?OUT LETTER", head, re.I) and not re.search(r"WARNING LETTER\s", head):
                row["note"] = "CHECK: saved page looks like a close-out letter, not the warning letter"
        if not pages:
            row["method"] += " - page found but could not be saved"
        log.append(row)
        print(f"  [{i + 1}/{len(letters)}] {row['found']:3} {out.name}", flush=True)

    log = pd.DataFrame(log)
    path = PROCESSED_DIR / f"warning_letter_pdf_log_{today}.xlsx"
    log.to_excel(path, index=False)
    print(log.found.value_counts().to_string())
    print(f"  -> {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
