# =============================================================
# Script: 02_link_warning_letters_to_gvkey.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medical Device Disclosure (Armando Cuello, EDBA)
# Purpose: Link the company names on FDA Warning Letters to Compustat firm
#          identifiers (gvkey) via WRDS, using a CONSERVATIVE, high-confidence
#          name match. Recipients that do not match cleanly are left UNMATCHED
#          and written to a separate file for manual linking later.
# Inputs:  data/processed/fda_warning_letters_<YYYY-MM-DD>.csv  (from script 01)
#          WRDS table comp.company                              (licensed; via WRDS)
# Outputs: data/raw/compustat_company_<YYYY-MM-DD>.csv          (the Compustat pull, untouched)
#          data/processed/warning_letter_gvkey_crosswalk_<YYYY-MM-DD>.csv (matched firms)
#          data/processed/warning_letter_unmatched_<YYYY-MM-DD>.csv       (for manual linking)
#
# Companion doc: data/warning_letter_gvkey_crosswalk_replication_instructions.md
#
# MATCHING PHILOSOPHY (agreed design choices):
#   * Scope   = ALL warning-letter recipients (not just device letters).
#   * Method  = CONSERVATIVE exact-ish match only. We normalize company names
#               (uppercase, strip punctuation and corporate suffixes) and accept
#               a link ONLY when a normalized name maps to EXACTLY ONE gvkey.
#               Names that map to zero or to multiple gvkeys are left unmatched.
#   * We DO NOT guess. Most FDA letter recipients are private/small/foreign
#     firms with no Compustat record; a low match rate is the correct, honest
#     outcome, not a bug. Precision is prioritized over recall.
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import os
import re
import sys
import glob
from datetime import date
from pathlib import Path
from collections import defaultdict

import pandas as pd
import wrds

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# WRDS username. Compustat is licensed, so a valid WRDS login is required.
# Set the WRDS_USERNAME environment variable to your own username; if it is not
# set we fall back to the maintainer's. The password is read automatically from
# the saved WRDS credential file (~/.pgpass or pgpass.conf) — see the
# replication doc for one-time setup.
WRDS_USERNAME = os.environ.get("WRDS_USERNAME", "rxb1406")


# =============================================================
# STEP 1. Company-name normalization
# =============================================================
# Company names are written inconsistently across sources ("Medtronic, Inc."
# vs "MEDTRONIC PLC"). To compare them we strip everything that is not part of
# the core name: case, punctuation, and corporate-form suffixes.

# Corporate-form suffixes removed before comparison. Split into a DOMESTIC and a
# FOREIGN family so we can later FLAG (not drop) matches where a US-style entity
# was matched to a foreign-style one — a common source of false positives
# (e.g., "Tropic Trading Co." vs "Tropic Trading Ltd").
DOMESTIC_FORMS = {"INC", "INCORPORATED", "LLC", "LP", "LLP", "CORP",
                  "CORPORATION", "CO", "COMPANY"}
FOREIGN_FORMS = {"LTD", "LIMITED", "PLC", "GMBH", "SA", "AG", "NV", "BV",
                 "PTE", "PVT", "AB", "SPA", "SRL", "OY", "AS"}
# Generic descriptors that are not entity forms but add no identifying value.
NOISE_TOKENS = {"THE", "DBA", "GROUP", "HOLDING", "HOLDINGS", "INTERNATIONAL",
                "INTL", "USA", "US"}

_ALL_STRIP = DOMESTIC_FORMS | FOREIGN_FORMS | NOISE_TOKENS
_SUFFIX_RE = r"\b(" + "|".join(sorted(_ALL_STRIP, key=len, reverse=True)) + r")\b"


def normalize_name(raw: str) -> str:
    """Return a comparison key: uppercase, no punctuation, no corporate suffix."""
    s = str(raw).upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)     # drop punctuation -> spaces
    s = re.sub(_SUFFIX_RE, " ", s)        # drop corporate/noise tokens
    s = re.sub(r"\s+", " ", s).strip()    # collapse whitespace
    return s


def entity_family(raw: str) -> str:
    """Classify a name's corporate form as 'domestic', 'foreign', or 'none'."""
    tokens = set(re.sub(r"[^A-Z ]", " ", str(raw).upper()).split())
    if tokens & FOREIGN_FORMS:
        return "foreign"
    if tokens & DOMESTIC_FORMS:
        return "domestic"
    return "none"


# =============================================================
# STEP 2. Pull the Compustat company table from WRDS
# =============================================================
def fetch_compustat_company(snapshot_date: str) -> pd.DataFrame:
    """
    Download comp.company (the Compustat firm master) and save the untouched
    pull to data/raw/. Saving it lets the match be re-run offline and makes the
    exact Compustat snapshot auditable.
    """
    print(f"  connecting to WRDS as '{WRDS_USERNAME}' ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        # conm/conml = company names; gvkey = target id; cik links to SEC EDGAR;
        # sic/naics = industry; costat = active/inactive status.
        company = db.raw_sql(
            "select gvkey, conm, conml, cik, sic, naics, costat "
            "from comp.company"
        )
    finally:
        db.close()

    raw_path = RAW_DIR / f"compustat_company_{snapshot_date}.csv"
    company.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"  pulled {len(company):,} Compustat firms -> "
          f"{raw_path.relative_to(REPO_ROOT)}")
    return company


# =============================================================
# STEP 3. Build the normalized-name -> gvkey lookup
# =============================================================
def build_name_lookup(company: pd.DataFrame):
    """
    Map each normalized Compustat name (from BOTH conm and conml) to the set of
    gvkeys that use it. A name mapping to >1 gvkey is ambiguous and will not be
    auto-matched.
    """
    lookup = defaultdict(set)
    conm_by_gvkey = dict(zip(company["gvkey"], company["conm"]))

    for _, row in company.iterrows():
        for name in (row["conm"], row["conml"]):
            key = normalize_name(name)
            if key:
                lookup[key].add(row["gvkey"])
    return lookup, conm_by_gvkey


# =============================================================
# STEP 4. Match recipients and split matched vs unmatched
# =============================================================
def match_recipients(wl: pd.DataFrame, lookup, conm_by_gvkey) -> pd.DataFrame:
    """
    For each unique recipient name, attempt a conservative exact-normalized
    match. Returns one row per unique recipient name with match results.
    """
    # One row per unique recipient name, with how many letters they received
    # and whether any of those letters is a device letter.
    grp = (wl.groupby("company_name_clean")
             .agg(n_letters=("company_name_clean", "size"),
                  any_device_letter=("is_device_letter", "max"))
             .reset_index())

    records = []
    for _, r in grp.iterrows():
        fda_name = r["company_name_clean"]
        key = normalize_name(fda_name)
        gvkeys = lookup.get(key, set())

        if len(gvkeys) == 1:
            gvkey = next(iter(gvkeys))
            comp_name = conm_by_gvkey[gvkey]
            # Precision guard: flag matches where the US/foreign entity family
            # differs between the FDA name and the Compustat name. These are the
            # most likely false positives and warrant a human glance.
            fam_fda, fam_comp = entity_family(fda_name), entity_family(comp_name)
            review = (fam_fda != "none" and fam_comp != "none"
                      and fam_fda != fam_comp)
            status = "matched"
        else:
            gvkey, comp_name, review, status = (
                None, None, False,
                "ambiguous" if len(gvkeys) > 1 else "unmatched")

        records.append({
            "company_name_fda": fda_name,
            "normalized_name": key,
            "match_status": status,
            "gvkey": gvkey,
            "company_name_compustat": comp_name,
            "n_gvkey_candidates": len(gvkeys),
            "review_suggested": review,
            "n_letters": int(r["n_letters"]),
            "any_device_letter": bool(r["any_device_letter"]),
        })

    return pd.DataFrame(records)


# =============================================================
# STEP 5. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Link FDA Warning Letters -> Compustat gvkey (WRDS)")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 60)

    # --- 5a. Load the most recent processed warning-letter file. ---
    wl_files = sorted(glob.glob(str(PROCESSED_DIR / "fda_warning_letters_*.csv")))
    if not wl_files:
        raise FileNotFoundError(
            "No processed warning-letter file found. Run "
            "scripts/01_fetch_fda_warning_letters.py first.")
    wl_path = Path(wl_files[-1])
    wl = pd.read_csv(wl_path)
    print(f"[1/4] Loaded {len(wl):,} letters from {wl_path.name} "
          f"({wl['company_name_clean'].nunique():,} unique recipients)")

    # --- 5b. Pull Compustat and build the lookup. ---
    print("[2/4] Pulling Compustat company master from WRDS ...")
    company = fetch_compustat_company(snapshot_date)
    lookup, conm_by_gvkey = build_name_lookup(company)

    # --- 5c. Match. ---
    print("[3/4] Matching recipient names to gvkey (conservative) ...")
    result = match_recipients(wl, lookup, conm_by_gvkey)

    matched = result[result["match_status"] == "matched"].copy()
    unmatched = result[result["match_status"] != "matched"].copy()

    crosswalk_path = (PROCESSED_DIR /
                      f"warning_letter_gvkey_crosswalk_{snapshot_date}.csv")
    unmatched_path = (PROCESSED_DIR /
                      f"warning_letter_unmatched_{snapshot_date}.csv")
    matched.sort_values("company_name_fda").to_csv(
        crosswalk_path, index=False, encoding="utf-8-sig")
    unmatched.sort_values("company_name_fda").to_csv(
        unmatched_path, index=False, encoding="utf-8-sig")

    # --- 5d. Summary. ---
    print("[4/4] Summary")
    print(f"  unique recipients         : {len(result):,}")
    print(f"  matched to gvkey          : {len(matched):,}")
    print(f"     - of which device firm : {int(matched['any_device_letter'].sum()):,}")
    print(f"     - flagged for review   : {int(matched['review_suggested'].sum()):,}")
    print(f"  ambiguous (>1 gvkey)      : {int((result.match_status=='ambiguous').sum()):,}")
    print(f"  unmatched (manual later)  : {int((result.match_status=='unmatched').sum()):,}")
    print(f"  crosswalk -> {crosswalk_path.relative_to(REPO_ROOT)}")
    print(f"  unmatched -> {unmatched_path.relative_to(REPO_ROOT)}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
