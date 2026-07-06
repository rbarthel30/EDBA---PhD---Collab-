# =============================================================
# Script: 03_fetch_fda_compliance_actions.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Acquire the FULL HISTORY of FDA compliance actions (Warning Letters,
#          Seizures, Injunctions) from the FDA Data Dashboard — fiscal years
#          2009 to present, ALL product types (Devices, Drugs, Biologics,
#          Food/Cosmetics, Tobacco, Veterinary) — and produce a cleaned,
#          analysis-ready table with product-type flags.
#
#          This REPLACES the coverage limitation of script 01: the fda.gov
#          website export is hard-capped at the most recent ~1,000 letters
#          (reaching back only to ~2021), while the Data Dashboard covers
#          ~174,000 letters back to October 2008.
#
# Source:  FDA Data Dashboard — Compliance Actions
#          https://datadashboard.fda.gov/oii/cd/complianceactions.htm
#
# Modes (the script picks automatically):
#   A. API mode (preferred, fully scriptable) — used when the environment
#      variables FDA_DASHBOARD_USER and FDA_DASHBOARD_KEY are set.
#      Credentials are FREE: request an authorization key via the
#      "OII Unified Logon" link on the dashboard page; FDA emails the key.
#      Endpoint: https://api-datadashboard.fda.gov/v1/compliance_actions
#   B. Manual-download mode — pass the path of a dashboard export as an
#      argument:  python scripts/03_fetch_fda_compliance_actions.py <file.csv>
#      (On the dashboard page: "Download Dataset" -> "Entire Dataset".)
#
# Outputs: data/raw/fda_compliance_actions_<YYYY-MM-DD>.csv        (untouched raw)
#          data/processed/fda_compliance_actions_<YYYY-MM-DD>.csv  (cleaned + flags)
#
# Companion doc: data/fda_compliance_actions_replication_instructions.md
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import os
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

API_URL = "https://api-datadashboard.fda.gov/v1/compliance_actions"
API_USER = os.environ.get("FDA_DASHBOARD_USER")   # the email used to register
API_KEY = os.environ.get("FDA_DASHBOARD_KEY")     # the key FDA emails back
API_PAGE_SIZE = 5000                              # documented API maximum

# Canonical column layout = the dashboard's own "Entire Dataset" CSV export.
# API field names differ slightly, so API results are renamed to match; both
# modes therefore yield byte-compatible raw files.
API_TO_CSV_COLUMNS = {
    "FEINumber":        "FEI Number",
    "LegalName":        "Legal Name",
    "State":            "State",
    "CountryName":      "Country/Area",
    "ProductType":      "Product Type",
    "ActionTakenDate":  "Action Taken Date",
    "ActionType":       "Action Type",
    "CaseInjunctionID": "Case/Injunction ID",
}
EXPECTED_COLUMNS = list(API_TO_CSV_COLUMNS.values())

# Sanity floor: the dataset held ~174,000 rows on 2026-07-06 and only grows.
# A download far below this signals a truncated/failed pull, not real data.
MIN_EXPECTED_ROWS = 150_000


# =============================================================
# STEP 1. Acquisition — API mode
# =============================================================
def fetch_via_api() -> pd.DataFrame:
    """
    Page through the compliance_actions API endpoint (5,000 rows per request,
    the documented maximum) until all records are retrieved. No filters are
    applied: we deliberately pull EVERY action type and product type and tag
    the relevant subsets in code, so the sample definition stays a
    transparent, editable choice (same philosophy as script 01).
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization-User": API_USER,
        "Authorization-Key": API_KEY,
    }
    rows, start, total = [], 1, None
    while True:
        body = {
            # Sorting by the primary key gives a stable order across pages.
            "sort": "CaseInjunctionID",
            "sortorder": "asc",
            "filters": {},
            "columns": list(API_TO_CSV_COLUMNS.keys()),
            "rows": API_PAGE_SIZE,
            "start": start,
            "returntotalcount": True,
        }
        resp = requests.post(API_URL, json=body, headers=headers, timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        # The API signals success with statuscode 400 (sic — per FDA docs).
        if payload.get("statuscode") != 400:
            raise RuntimeError(f"API error: {payload.get('statuscode')} "
                               f"{payload.get('message')}")
        batch = payload.get("result", [])
        rows.extend(batch)
        total = payload.get("totalrecordcount", total)
        print(f"    fetched {len(rows):,} / {total:,} records ...")
        if not batch or len(rows) >= (total or 0):
            break
        start += len(batch)

    df = pd.DataFrame(rows).rename(columns=API_TO_CSV_COLUMNS)
    return df[EXPECTED_COLUMNS]


# =============================================================
# STEP 2. Acquisition — manual-download mode
# =============================================================
def load_manual_download(path: Path) -> pd.DataFrame:
    """
    Read a CSV exported by hand from the dashboard ("Download Dataset" ->
    "Entire Dataset"). Validates the column layout so a wrong file (e.g., a
    filtered export or a graph export) is rejected loudly rather than
    processed silently.
    """
    df = pd.read_csv(path)
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path.name} is missing expected columns {missing}. "
            "Make sure you exported 'Entire Dataset' from the Compliance "
            "Actions dashboard (not a filtered or graph export).")
    return df[EXPECTED_COLUMNS]


# =============================================================
# STEP 3. Cleaning and product-type flags
# =============================================================
def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse dates, standardize company names, and add analysis flags. All raw
    columns are preserved; everything added is a new, clearly named column.
    """
    out = df.copy()

    # --- 3a. Drop tobacco letters (design decision, Ryan 2026-07-06). ~95%
    # of dashboard warning letters are tobacco-retailer letters (corner
    # stores and vape shops cited for selling to minors) — irrelevant to the
    # project and they swamp every downstream file. The RAW snapshot keeps
    # them (raw is sacred); the processed file excludes them permanently.
    n_before = len(out)
    out = out[out["Product Type"].astype(str) != "Tobacco"].copy()
    print(f"    dropped {n_before - len(out):,} tobacco rows "
          f"({len(out):,} remain)")

    # --- 3b. Dates. The dashboard CSV uses MM/DD/YYYY; the API returns ISO
    # (YYYY-MM-DD). Try the CSV format first, then fall back to ISO.
    parsed = pd.to_datetime(out["Action Taken Date"],
                            format="%m/%d/%Y", errors="coerce")
    iso = pd.to_datetime(out["Action Taken Date"],
                         format="%Y-%m-%d", errors="coerce")
    out["action_taken_date"] = parsed.fillna(iso)
    n_bad = int(out["action_taken_date"].isna().sum())
    if n_bad:
        print(f"    WARNING: {n_bad} rows have unparseable dates")

    # --- 3c. Company name: collapse internal whitespace (same convention as
    # script 01's company_name_clean, so downstream matching code is shared).
    out["company_name_clean"] = (out["Legal Name"].astype(str)
                                 .str.split().str.join(" "))

    # --- 3d. Action-type flag. Warning Letters are the project's treatment
    # event; seizures/injunctions are kept for completeness but flagged off.
    out["is_warning_letter"] = out["Action Type"].eq("Warning Letter")

    # --- 3e. Product-type flags, straight from FDA's own classification —
    # no keyword guessing (unlike script 01, which had to infer device
    # letters from office/subject text). One letter can span product types.
    pt = out["Product Type"].astype(str)
    out["is_device"] = pt.eq("Devices")
    out["is_drug"] = pt.eq("Drugs")
    out["is_biologic"] = pt.eq("Biologics")
    # The project's analysis universe: medtech + pharma + biologics.
    out["is_medtech_pharma"] = out["is_device"] | out["is_drug"] | out["is_biologic"]

    return out


# =============================================================
# STEP 4. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / f"fda_compliance_actions_{snapshot_date}.csv"
    processed_path = PROCESSED_DIR / f"fda_compliance_actions_{snapshot_date}.csv"

    print("=" * 60)
    print("FDA Compliance Actions (Data Dashboard) — full history")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 60)

    # --- 4a. Acquire (mode picked automatically). ---
    manual_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if manual_file is not None:
        print(f"[1/3] Manual mode: reading {manual_file} ...")
        df = load_manual_download(manual_file)
        # Preserve the hand-downloaded file byte-for-byte as the raw snapshot.
        shutil.copyfile(manual_file, raw_path)
    elif API_USER and API_KEY:
        print("[1/3] API mode: pulling from api-datadashboard.fda.gov ...")
        df = fetch_via_api()
        df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    else:
        raise SystemExit(
            "No acquisition mode available.\n"
            "  EITHER set FDA_DASHBOARD_USER / FDA_DASHBOARD_KEY (free key via\n"
            "  the OII Unified Logon link on the dashboard page)\n"
            "  OR download 'Entire Dataset' from\n"
            "  https://datadashboard.fda.gov/oii/cd/complianceactions.htm\n"
            "  and run: python scripts/03_fetch_fda_compliance_actions.py <file.csv>")

    if len(df) < MIN_EXPECTED_ROWS:
        raise RuntimeError(
            f"Only {len(df):,} rows retrieved (expected >= {MIN_EXPECTED_ROWS:,}). "
            "The download looks truncated — not saving a processed file.")
    print(f"    raw snapshot ({len(df):,} rows) -> {raw_path.relative_to(REPO_ROOT)}")

    # --- 4b. Clean + flag. ---
    print("[2/3] Cleaning and adding product-type flags ...")
    out = clean(df)
    out.to_csv(processed_path, index=False, encoding="utf-8-sig")
    print(f"    processed -> {processed_path.relative_to(REPO_ROOT)}")

    # --- 4c. Summary. ---
    wl = out[out["is_warning_letter"]]
    print("[3/3] Summary")
    print(f"  total rows                : {len(out):,}")
    print(f"  date range                : {out['action_taken_date'].min().date()} "
          f"to {out['action_taken_date'].max().date()}")
    print(f"  warning letters           : {len(wl):,}")
    print(f"     - device               : {int(wl['is_device'].sum()):,}")
    print(f"     - drug                 : {int(wl['is_drug'].sum()):,}")
    print(f"     - biologic             : {int(wl['is_biologic'].sum()):,}")
    print(f"     - medtech+pharma total : {int(wl['is_medtech_pharma'].sum()):,}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
