# =============================================================
# Script: 01_fetch_fda_warning_letters.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medical Device Disclosure (Armando Cuello, EDBA)
# Purpose: Download the FDA Warning Letters database, parse it into a clean
#          firm-letter table, and flag the medical-device-relevant letters.
# Inputs:  Live FDA Warning Letters web service (no local input file).
#          URL: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/
#               compliance-actions-and-activities/warning-letters
# Outputs: data/raw/fda_warning_letters_<YYYY-MM-DD>.xlsx        (untouched download)
#          data/processed/fda_warning_letters_<YYYY-MM-DD>.csv   (cleaned + device-tagged)
#
# Companion doc: data/fda_warning_letters_replication_instructions.md
#   -> Read that file first. It explains, in plain language, where this data
#      comes from, the one important coverage limitation, and how to re-run
#      this script from a clean machine.
#
# NOTE ON COVERAGE (important — see replication doc for full detail):
#   The FDA's public bulk export returns the MOST RECENT 1,000 warning letters
#   (all FDA centers, roughly the last ~5 years). The site lists ~3,500 letters
#   in total, but it does NOT expose the older ones through any stable, scriptable
#   download (the pager is JavaScript-only and there is no date-range filter on
#   the export). This script therefore captures the most-recent-1,000 snapshot,
#   which is complete and reproducible for that window. Options for back-filling
#   older letters are documented in the replication markdown.
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import io
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# --- Resolve project paths relative to this script (never hard-code absolute paths) ---
# This file lives in <repo>/scripts/, so the repo root is its parent's parent.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# --- The FDA "datatables-data" endpoint returns the warning-letter table as an
#     Excel (.xlsx) export. This is the only stable, no-JavaScript bulk download
#     the site offers. We discovered it by reading the page's own DataTables
#     configuration (documented in the replication markdown). ---
FDA_PAGE_URL = (
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
    "compliance-actions-and-activities/warning-letters"
)
FDA_EXPORT_URL = FDA_PAGE_URL + "/datatables-data"

# --- The export endpoint only returns data when it receives the DataTables /
#     Drupal view request signature below. WITHOUT these query parameters it
#     returns a structurally valid but EMPTY spreadsheet, so they are required,
#     not optional. `view_name` + `view_display_id` tell the endpoint which view
#     to export; `draw/start/length` are the standard DataTables paging fields. ---
FDA_EXPORT_PARAMS = {
    "draw": "1",
    "start": "0",
    "length": "10",          # ignored by the export (it returns the full set), but expected
    "_drupal_ajax": "1",
    "view_name": "warning_letter_solr_index",
    "view_display_id": "warning_letter_solr_block",
}

# --- Request headers. Two of these are functionally REQUIRED, not cosmetic:
#       * "X-Requested-With: XMLHttpRequest" — the export treats the request as
#         an AJAX call ONLY when this header is present. WITHOUT it the endpoint
#         returns a valid but EMPTY spreadsheet (a silent-failure trap we hit
#         and diagnosed during development). This is the single most important
#         header here.
#       * "Referer" — identifies the warning-letters page as the origin, which
#         the endpoint expects.
#     A descriptive User-Agent (with a contact email) is good scraping etiquette
#     for a public government site. ---
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (academic research; rbarthel15@gmail.com)",
    "Referer": FDA_PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# Number of times to retry if the FDA edge server returns a bad response
# (the transient HTTP 503 "apology" page, OR a valid-but-EMPTY spreadsheet).
MAX_RETRIES = 6
RETRY_WAIT_SECONDS = 5

# The columns we expect every genuine export to contain. We validate against
# these so an empty or malformed download is caught and retried, never saved.
EXPECTED_COLUMNS = {"Posted Date", "Letter Issue Date", "Company Name",
                    "Issuing Office", "Subject"}
# A genuine snapshot contains ~1,000 letters. Treat anything implausibly small
# as a failed/empty download and retry.
MIN_PLAUSIBLE_ROWS = 100


# =============================================================
# STEP 1. Download the raw warning-letter spreadsheet from FDA
# =============================================================
def download_warning_letters() -> bytes:
    """
    Fetch the FDA warning-letter export and return the raw .xlsx bytes.

    Why a retry loop with validation: the FDA site sits behind a CDN (Akamai)
    that, under load, can return EITHER (a) a generic HTML "apology" page
    (HTTP 503), or (b) a structurally valid but completely EMPTY spreadsheet.
    Both are useless, and (b) is dangerous because it parses without error. We
    therefore validate every response on three counts before accepting it:
        1. Content-Type advertises a spreadsheet,
        2. the parsed sheet contains the expected columns, and
        3. it holds a plausible number of rows.
    Anything failing these checks is retried, so we never save a bad snapshot.

    Why a primed session: hitting the warning-letters page first lets the CDN
    set the cookies it expects on the subsequent export request, which makes a
    good (non-empty) response far more reliable.
    """
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    # Prime the session: load the human-facing page once so the CDN issues its
    # session cookies before we request the export.
    try:
        session.get(FDA_PAGE_URL, timeout=60)
    except requests.RequestException:
        pass  # Non-fatal; the export request below has its own retry guard.

    for attempt in range(1, MAX_RETRIES + 1):
        response = session.get(FDA_EXPORT_URL, params=FDA_EXPORT_PARAMS, timeout=120)
        content_type = response.headers.get("content-type", "")

        if "spreadsheet" in content_type:
            # Parse defensively to confirm the spreadsheet is real and non-empty.
            try:
                preview = pd.read_excel(io.BytesIO(response.content))
            except Exception:  # noqa: BLE001 - any parse failure -> retry
                preview = pd.DataFrame()

            has_columns = EXPECTED_COLUMNS.issubset(set(preview.columns))
            has_rows = len(preview) >= MIN_PLAUSIBLE_ROWS

            if has_columns and has_rows:
                print(f"  [download] success on attempt {attempt} "
                      f"({len(response.content):,} bytes, {len(preview):,} rows)")
                return response.content

            print(f"  [download] attempt {attempt}/{MAX_RETRIES} returned a "
                  f"spreadsheet but it was empty/malformed "
                  f"(rows={len(preview)}). Retrying...")
        else:
            # We hit the transient HTML error page instead of the export.
            print(f"  [download] attempt {attempt}/{MAX_RETRIES} returned "
                  f"status={response.status_code}, content-type='{content_type}'. "
                  "Retrying...")

        time.sleep(RETRY_WAIT_SECONDS)

    # If we exhaust all retries, fail loudly rather than producing a partial file.
    raise RuntimeError(
        "Could not retrieve a valid FDA warning-letter spreadsheet after "
        f"{MAX_RETRIES} attempts. The FDA site may be temporarily unavailable "
        "or rate-limiting; wait a few minutes and re-run."
    )


# =============================================================
# STEP 2. Flag the medical-device-relevant warning letters
# =============================================================
# We follow the agreed "pull everything, then tag" approach: keep the full
# download intact (raw is sacred) and add boolean flags identifying the
# device-relevant subset. This lets the device definition be revised later
# WITHOUT re-downloading, and keeps every classification rule auditable.
#
# A letter is treated as device-relevant if EITHER:
#   (a) its Issuing Office is a device-review office, OR
#   (b) its Subject names a device-specific regulatory program.
# We record (a) and (b) separately so the sample can be tightened or loosened
# (e.g., office-only) without changing this code.
#
# -------------------------------------------------------------
# >>> RESEARCH-DESIGN DECISION POINT (Ryan / Armando) <<<
#     These two keyword lists define the medical-device sample. They are the
#     single most consequential judgment call in this script. Review them and
#     edit as needed — e.g., decide whether COVID-era device letters or
#     Good Laboratory Practice (GLP) letters belong in the device subset.
#     Any change here is fully traceable and requires no re-download.
# -------------------------------------------------------------

# (a) Issuing offices that review medical devices. CDRH is the Center for
#     Devices and Radiological Health; its inspection work is also issued under
#     "Office of Medical Device and Radiological Health" district offices and
#     "OHT" (Office of Health Technology) cardiovascular/etc. sub-offices.
DEVICE_OFFICE_PATTERNS = [
    r"Devices and Radiological Health",   # CDRH (headquarters)
    r"Office of Medical Device",          # district medical-device offices
    r"OHT\d",                             # OHT1..OHT8 product-evaluation offices
    r"Cardiovascular Devices",            # named device product office
]

# (b) Subject-line programs that are specific to medical devices.
#     QSR = Quality System Regulation (21 CFR 820); 510(k) = premarket
#     notification; PMA = Premarket Approval; IDE = Investigational Device
#     Exemption; MDR = Medical Device Reporting.
DEVICE_SUBJECT_PATTERNS = [
    r"Medical Device",
    r"\bQSR\b",
    r"Quality System Regulation",
    r"21 CFR 820",
    r"510\(k\)",
    r"Premarket Approval",
    r"\bPMA\b",
    r"Investigational Device Exemption",
    r"\bIDE\b",
    r"Device Reporting",
]


def tag_device_letters(df: pd.DataFrame) -> pd.DataFrame:
    """Add device_by_office, device_by_subject, and is_device_letter flags."""
    office = df["Issuing Office"].fillna("")
    subject = df["Subject"].fillna("")

    # case=False so we match regardless of capitalization; regex=True so the
    # patterns above (with \b word boundaries etc.) are honored.
    office_pattern = "|".join(DEVICE_OFFICE_PATTERNS)
    subject_pattern = "|".join(DEVICE_SUBJECT_PATTERNS)

    df = df.copy()
    df["device_by_office"] = office.str.contains(office_pattern, case=False, regex=True)
    df["device_by_subject"] = subject.str.contains(subject_pattern, case=False, regex=True)
    df["is_device_letter"] = df["device_by_office"] | df["device_by_subject"]
    return df


# =============================================================
# STEP 3. Clean and standardize the downloaded table
# =============================================================
def clean_warning_letters(raw_bytes: bytes) -> pd.DataFrame:
    """Parse the .xlsx bytes into a tidy, analysis-ready DataFrame."""
    df = pd.read_excel(io.BytesIO(raw_bytes))

    # --- Parse the two date columns to real datetimes (FDA serves MM/DD/YYYY). ---
    # Keep the original string columns untouched and add parsed *_date columns,
    # so nothing is lost if a value fails to parse.
    df["posted_date"] = pd.to_datetime(df["Posted Date"], errors="coerce")
    df["letter_issue_date"] = pd.to_datetime(df["Letter Issue Date"], errors="coerce")

    # --- Trim stray whitespace in the free-text company name. ---
    df["company_name_clean"] = (
        df["Company Name"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    )

    # --- Add the medical-device flags (Step 2). ---
    df = tag_device_letters(df)

    # --- Sort newest-first for readability; this does not affect analysis. ---
    df = df.sort_values("posted_date", ascending=False).reset_index(drop=True)
    return df


# =============================================================
# STEP 4. Orchestrate: download -> save raw -> clean -> save processed
# =============================================================
def main() -> None:
    # Date-stamp every artifact so a download can always be tied to its snapshot
    # date (per the project's data-hygiene rule: "Date-stamp downloads").
    today = date.today().isoformat()  # e.g. "2026-06-08"

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / f"fda_warning_letters_{today}.xlsx"
    processed_path = PROCESSED_DIR / f"fda_warning_letters_{today}.csv"

    print("=" * 60)
    print("FDA Warning Letters — fetch & tag")
    print(f"Snapshot date: {today}")
    print("=" * 60)

    # --- 4a. Download and save the untouched raw file. ---
    print("[1/3] Downloading from FDA ...")
    raw_bytes = download_warning_letters()
    raw_path.write_bytes(raw_bytes)
    print(f"  saved raw  -> {raw_path.relative_to(REPO_ROOT)}")

    # --- 4b. Clean, parse, and tag. ---
    print("[2/3] Cleaning and tagging device letters ...")
    df = clean_warning_letters(raw_bytes)

    # --- 4c. Save the processed, analysis-ready table. ---
    df.to_csv(processed_path, index=False, encoding="utf-8-sig")
    print(f"  saved processed -> {processed_path.relative_to(REPO_ROOT)}")

    # -------------------------------------------------------------
    # Snapshot summary (printed so each run leaves an auditable record).
    # -------------------------------------------------------------
    n_total = len(df)
    n_device = int(df["is_device_letter"].sum())
    n_office = int(df["device_by_office"].sum())
    n_subject = int(df["device_by_subject"].sum())
    date_min = df["posted_date"].min()
    date_max = df["posted_date"].max()

    print("[3/3] Summary")
    print(f"  total letters in snapshot : {n_total:,}")
    print(f"  posted-date range         : {date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}")
    print(f"  device letters (either)   : {n_device:,}")
    print(f"     - flagged by office    : {n_office:,}")
    print(f"     - flagged by subject   : {n_subject:,}")
    print("Done.")


if __name__ == "__main__":
    # Surface any failure with a non-zero exit code so it is obvious in logs.
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
