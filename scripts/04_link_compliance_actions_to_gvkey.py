# =============================================================
# Script: 04_link_compliance_actions_to_gvkey.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Link the recipient names on the FULL-HISTORY FDA warning-letter
#          dataset (from script 03; FY2009-present, all product types) to
#          Compustat firm identifiers (gvkey) via WRDS, using the same
#          CONSERVATIVE, high-confidence name match as script 02.
#          Recipients that do not match cleanly are left UNMATCHED and the
#          medtech/pharma subset of them is written out for manual linking.
# Inputs:  data/processed/fda_compliance_actions_<YYYY-MM-DD>.csv (from script 03)
#          WRDS table comp.company                                (licensed; via WRDS)
# Outputs: data/raw/compustat_company_<YYYY-MM-DD>.csv            (the Compustat pull, untouched)
#          data/processed/compliance_actions_gvkey_crosswalk_<YYYY-MM-DD>.csv (matched firms)
#          data/processed/compliance_actions_unmatched_<YYYY-MM-DD>.csv       (medtech/pharma only)
#
# Companion doc: data/compliance_actions_gvkey_crosswalk_replication_instructions.md
#
# MATCHING PHILOSOPHY (unchanged from script 02):
#   * Scope   = ALL warning-letter recipients, every product type. Matches
#               outside medtech/pharma (e.g., big food or tobacco firms) are
#               kept in the crosswalk — they cost nothing and may be useful.
#   * Method  = CONSERVATIVE exact-ish match only. We normalize company names
#               (uppercase, strip punctuation and corporate suffixes) and accept
#               a link ONLY when a normalized name maps to EXACTLY ONE gvkey.
#   * We DO NOT guess. Most recipients are private/small/foreign firms (and,
#     in this full dataset, ~165k of 174k letters go to tobacco retailers —
#     corner stores and vape shops that have no Compustat record). A low
#     match RATE is the correct, honest outcome. Precision over recall.
#   * The UNMATCHED file is limited to medtech/pharma recipients (device,
#     drug, biologic letters). That is the universe worth manually linking;
#     including ~120k unmatched tobacco shops would bury the real work.
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

# WRDS username (see script 02 / replication doc for one-time password setup).
WRDS_USERNAME = os.environ.get("WRDS_USERNAME", "rxb1406")


# =============================================================
# STEP 1. Company-name normalization
# =============================================================
# Identical rules to script 02 (kept in sync BY HAND — if you edit one,
# edit the other): uppercase, strip punctuation and corporate-form suffixes,
# and classify the entity form so cross-family matches can be flagged.

DOMESTIC_FORMS = {"INC", "INCORPORATED", "LLC", "LP", "LLP", "CORP",
                  "CORPORATION", "CO", "COMPANY"}
FOREIGN_FORMS = {"LTD", "LIMITED", "PLC", "GMBH", "SA", "AG", "NV", "BV",
                 "PTE", "PVT", "AB", "SPA", "SRL", "OY", "AS"}
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
    pull to data/raw/ (gitignored — WRDS terms prohibit redistribution).
    """
    print(f"  connecting to WRDS as '{WRDS_USERNAME}' ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
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
    Map each normalized Compustat name (from BOTH conm and conml) to the set
    of gvkeys that use it. A name mapping to >1 gvkey is ambiguous and will
    not be auto-matched.
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
# STEP 4. Collapse letters to one row per recipient name
# =============================================================
def summarize_recipients(wl: pd.DataFrame) -> pd.DataFrame:
    """
    One row per unique recipient name. A single warning letter (Case ID) can
    appear on multiple rows in the letter file (one per establishment and
    product type), so letter counts use UNIQUE Case/Injunction IDs.
    """
    grp = (wl.groupby("company_name_clean")
             .agg(n_letters=("Case/Injunction ID", "nunique"),
                  first_letter_date=("action_taken_date", "min"),
                  last_letter_date=("action_taken_date", "max"),
                  any_device_letter=("is_device", "max"),
                  any_drug_letter=("is_drug", "max"),
                  any_biologic_letter=("is_biologic", "max"),
                  any_medtech_pharma=("is_medtech_pharma", "max"),
                  product_types=("Product Type",
                                 lambda s: "; ".join(sorted(set(s.astype(str))))))
             .reset_index())
    return grp


# =============================================================
# STEP 5. Match recipients and split matched vs unmatched
# =============================================================
def match_recipients(grp: pd.DataFrame, lookup, conm_by_gvkey) -> pd.DataFrame:
    """
    For each unique recipient name, attempt the conservative exact-normalized
    match (identical acceptance rule to script 02).
    """
    records = []
    for _, r in grp.iterrows():
        fda_name = r["company_name_clean"]
        key = normalize_name(fda_name)
        gvkeys = lookup.get(key, set())

        if len(gvkeys) == 1:
            gvkey = next(iter(gvkeys))
            comp_name = conm_by_gvkey[gvkey]
            # Precision guard: flag matches whose US/foreign entity family
            # differs between the FDA and Compustat names (likeliest false
            # positives — worth a human glance).
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
            "first_letter_date": r["first_letter_date"],
            "last_letter_date": r["last_letter_date"],
            "any_device_letter": bool(r["any_device_letter"]),
            "any_drug_letter": bool(r["any_drug_letter"]),
            "any_biologic_letter": bool(r["any_biologic_letter"]),
            "any_medtech_pharma": bool(r["any_medtech_pharma"]),
            "product_types": r["product_types"],
        })

    return pd.DataFrame(records)


# =============================================================
# STEP 6. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Link FDA Compliance-Action Warning Letters -> Compustat gvkey")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 60)

    # --- 6a. Load the most recent processed compliance-actions file. ---
    ca_files = sorted(glob.glob(str(PROCESSED_DIR / "fda_compliance_actions_*.csv")))
    if not ca_files:
        raise FileNotFoundError(
            "No processed compliance-actions file found. Run "
            "scripts/03_fetch_fda_compliance_actions.py first.")
    ca_path = Path(ca_files[-1])
    ca = pd.read_csv(ca_path, parse_dates=["action_taken_date"])

    # Warning letters are the treatment event; seizures/injunctions excluded.
    wl = ca[ca["is_warning_letter"]].copy()
    print(f"[1/4] Loaded {len(wl):,} warning-letter rows from {ca_path.name} "
          f"({wl['company_name_clean'].nunique():,} unique recipients)")

    # --- 6b. Pull Compustat and build the lookup. ---
    print("[2/4] Pulling Compustat company master from WRDS ...")
    company = fetch_compustat_company(snapshot_date)
    lookup, conm_by_gvkey = build_name_lookup(company)

    # --- 6c. Match. ---
    print("[3/4] Matching recipient names to gvkey (conservative) ...")
    grp = summarize_recipients(wl)
    result = match_recipients(grp, lookup, conm_by_gvkey)

    matched = result[result["match_status"] == "matched"].copy()
    # Unmatched output limited to the medtech/pharma universe (see header).
    unmatched = result[(result["match_status"] != "matched")
                       & result["any_medtech_pharma"]].copy()

    crosswalk_path = (PROCESSED_DIR /
                      f"compliance_actions_gvkey_crosswalk_{snapshot_date}.csv")
    unmatched_path = (PROCESSED_DIR /
                      f"compliance_actions_unmatched_{snapshot_date}.csv")
    matched.sort_values("company_name_fda").to_csv(
        crosswalk_path, index=False, encoding="utf-8-sig")
    unmatched.sort_values("company_name_fda").to_csv(
        unmatched_path, index=False, encoding="utf-8-sig")

    # --- 6d. Summary. ---
    mp = matched[matched["any_medtech_pharma"]]
    print("[4/4] Summary")
    print(f"  unique recipients               : {len(result):,}")
    print(f"     - of which medtech/pharma    : {int(result['any_medtech_pharma'].sum()):,}")
    print(f"  matched to gvkey (all types)    : {len(matched):,}")
    print(f"     - medtech/pharma firms       : {len(mp):,}")
    print(f"         * device                 : {int(mp['any_device_letter'].sum()):,}")
    print(f"         * drug                   : {int(mp['any_drug_letter'].sum()):,}")
    print(f"         * biologic               : {int(mp['any_biologic_letter'].sum()):,}")
    print(f"     - flagged for review         : {int(matched['review_suggested'].sum()):,}")
    print(f"  medtech/pharma left unmatched   : {len(unmatched):,}")
    print(f"  crosswalk -> {crosswalk_path.relative_to(REPO_ROOT)}")
    print(f"  unmatched -> {unmatched_path.relative_to(REPO_ROOT)}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
