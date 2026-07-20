# =============================================================
# Script: 13_fetch_device_classification.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Pull FDA's DEVICE CLASSIFICATION database and build a clean
#          product-code lookup that can be joined onto BOTH stages of the
#          regulatory timeline:
#
#            Part 803 MAUDE  --(device_report_product_code)--\
#                                                             >-- classification
#            Part 806 recalls --(product_code)---------------/
#
#          Both FDA sources carry the same 3-letter product code, so one
#          lookup gives consistent device categories across the whole panel.
#
# Source:  openFDA device/classification - 7,075 records, single partition.
#
# ---------------------------------------------------------------------------
# WHY THIS IS WORTH A SCRIPT (what it fixes):
#   VERIFIED 2026-07-19 - what this lookup does and does NOT fix:
#
#   DOES NOT FIX: MAUDE's 42% 'Unknown' medical_specialty (4.5M of 10.7M
#     reports). Those product codes are classified 'Unknown' in FDA's OWN
#     classification table too, so the join recovers essentially none of them.
#     'Unknown' is FDA's actual answer, not a MAUDE data gap. Any analysis
#     needing device category must treat ~42% of MAUDE as uncategorized, or
#     fall back on `device_report_product_code` itself (2,902 distinct codes,
#     100% populated) as a high-dimensional category.
#
#   DOES NOT FIX: `device_class`. MAUDE's own value agrees with the
#     authoritative one on 100% of comparable records, so MAUDE's field was
#     already trustworthy. (The stray 'f'/'U'/'N' values are ~0.3% and simply
#     coerce to missing.)
#
#   GENUINELY ADDS, none of which exist in MAUDE:
#     * `regulation_number` - the 21 CFR citation for the device type
#     * `life_sustain_support_flag` - life-sustaining/life-supporting device
#     * `implant_flag` - populated for all codes (MAUDE's own is 0.4%)
#     * `gmp_exempt_flag`, `third_party_flag`, `summary_malfunction_reporting`
#     * `device_name` / `definition` - cleaner than MAUDE's free-text
#       `generic_name`
#   Those flags are the substantive gain: implantable and life-sustaining
#   devices carry very different disclosure stakes, and neither is usable
#   from MAUDE alone.
# ---------------------------------------------------------------------------
#
# DESIGN NOTE - LOOKUP, NOT A REWRITE:
#   This script does NOT write enriched copies of the 803/806 files. The MAUDE
#   output alone is 555 MB and 10.7M rows; duplicating it to bolt on ~10
#   columns would cost disk and create a second file that can drift from the
#   first. Instead it emits a small joinable lookup keyed on product_code, and
#   downstream scripts join at analysis time.
#
# ---------------------------------------------------------------------------
# CAVEAT - `submission_type_id` IS AN UNMAPPED FDA-INTERNAL CODE.
#   It is a small integer whose meaning (510(k) / PMA / De Novo / exempt) is
#   NOT documented in the openFDA field reference. It is carried through
#   UNINTERPRETED. Do not treat it as a regulatory-pathway indicator until the
#   mapping is confirmed against FDA documentation. For pathway questions use
#   `device_class` (Class III is broadly the PMA population) together with
#   `regulation_number`, both of which are documented.
# ---------------------------------------------------------------------------
#
# Inputs:  (none required - pulls from openFDA)
#          data/processed/part803_adverse_events_<DATE>.csv.gz   (optional, for coverage)
#          data/raw/fda_device_recalls_<DATE>.csv                (optional, for coverage)
# Outputs: data/raw/fda_device_classification_<DATE>.csv         (universe, untouched)
#          data/processed/device_product_code_lookup_<DATE>.csv  (joinable lookup)
#
# Usage:   python scripts/13_fetch_device_classification.py
#          python scripts/13_fetch_device_classification.py --skip-coverage
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import io
import sys
import glob
import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

DOWNLOAD_MANIFEST = "https://api.fda.gov/download.json"

# Sanity floor: 7,075 records on 2026-07-19. This table grows slowly (new
# product codes as devices are classified), so a much smaller pull is a
# truncated download rather than real data.
MIN_EXPECTED_ROWS = 6_500

# Columns kept from the classification table, in the order they are written.
CLASSIFICATION_COLUMNS = [
    "product_code",                     # 3-letter key - joins to 803 and 806
    "device_name",
    "device_class",                     # authoritative risk class (1/2/3)
    "medical_specialty",                # 2-letter code
    "medical_specialty_description",    # human-readable panel
    "review_panel",
    "regulation_number",                # 21 CFR citation
    "definition",
    "implant_flag",
    "life_sustain_support_flag",
    "gmp_exempt_flag",
    "third_party_flag",
    "summary_malfunction_reporting",
    "submission_type_id",               # UNMAPPED - see caveat in header
    "unclassified_reason",
]


def latest(directory: Path, pattern: str):
    """Return the most recent date-stamped file matching a glob, or None."""
    hits = sorted(glob.glob(str(directory / pattern)))
    return Path(hits[-1]) if hits else None


# =============================================================
# STEP 1. Download the classification table
# =============================================================
def fetch_classification() -> pd.DataFrame:
    """
    Download the openFDA device/classification bulk export.

    Uses the bulk file rather than the paged API for the same reason as script
    10: it is a single partition, needs no authorization key, and carries a
    citable export_date.
    """
    manifest = requests.get(DOWNLOAD_MANIFEST, timeout=120).json()
    node = manifest["results"]["device"]["classification"]
    part = node["partitions"][0]
    print(f"    manifest: export_date={node['export_date']}, "
          f"{node['total_records']:,} records ({part['size_mb']} MB)")

    resp = requests.get(part["file"], timeout=600)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            payload = json.load(fh)
    records = payload.get("results", [])

    if len(records) < MIN_EXPECTED_ROWS:
        raise RuntimeError(
            f"Only {len(records):,} classification records retrieved "
            f"(expected >= {MIN_EXPECTED_ROWS:,}). Download looks truncated.")

    df = pd.json_normalize(records)
    missing = [c for c in CLASSIFICATION_COLUMNS if c not in df.columns]
    if missing:
        print(f"    NOTE: columns absent from this release: {missing}")
        for c in missing:
            df[c] = pd.NA
    return df[CLASSIFICATION_COLUMNS].copy()


# =============================================================
# STEP 2. Clean into a joinable lookup
# =============================================================
def build_lookup(df: pd.DataFrame) -> pd.DataFrame:
    """
    Produce one clean row per product_code.

    Column names are prefixed `dev_` so that a join onto the MAUDE or recall
    panels cannot silently collide with those files' own `device_class` /
    `medical_specialty` columns - the whole point is to be able to compare
    FDA's authoritative value against the one carried on the report.
    """
    out = df.copy()
    out["product_code"] = out["product_code"].astype(str).str.strip().str.upper()

    # Blank strings are missing data; make that explicit so downstream
    # notna() checks behave.
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].replace(r"^\s*$", pd.NA, regex=True)

    # Risk class as a nullable integer. The classification table is clean
    # (unlike MAUDE's copy), but coerce defensively rather than assume.
    out["device_class_num"] = pd.to_numeric(out["device_class"],
                                            errors="coerce").astype("Int64")

    # Y/N flags -> booleans, leaving anything unexpected as missing.
    for flag in ["implant_flag", "life_sustain_support_flag",
                 "gmp_exempt_flag", "third_party_flag"]:
        out[f"{flag}_bool"] = out[flag].map({"Y": True, "N": False})

    n_dupes = int(out["product_code"].duplicated().sum())
    if n_dupes:
        # A product code should be unique in this table. If FDA ships
        # duplicates, keep the first and say so rather than silently
        # multiplying rows on every downstream join.
        print(f"    WARNING: {n_dupes} duplicate product_code rows - keeping first")
        out = out.drop_duplicates("product_code", keep="first")

    rename = {c: f"dev_{c}" for c in out.columns if c != "product_code"}
    out = out.rename(columns=rename)
    return out


# =============================================================
# STEP 3. Coverage against the timeline datasets
# =============================================================
def report_coverage(lookup: pd.DataFrame) -> None:
    """
    Measure how much of the 803 and 806 data this lookup actually resolves,
    and - the point of the exercise - how much of MAUDE's 'Unknown' medical
    specialty it recovers.

    Coverage is reported rather than enforced: a product code present in MAUDE
    but absent from the classification table is a real FDA data gap, not a bug
    to be silently dropped.
    """
    codes = set(lookup["product_code"])

    # --- 3a. Part 806 recalls. ---
    rec_path = latest(RAW_DIR, "fda_device_recalls_*.csv")
    if rec_path is not None:
        rec = pd.read_csv(rec_path, low_memory=False, usecols=["product_code"])
        pc = rec["product_code"].astype(str).str.strip().str.upper()
        hit = pc.isin(codes)
        print(f"    806 recalls  : {hit.sum():,} of {len(pc):,} records "
              f"resolved ({hit.mean():.1%}); "
              f"{pc.nunique():,} distinct codes")

    # --- 3b. Part 803 MAUDE, plus the 'Unknown' specialty recovery. ---
    mau_path = latest(PROCESSED_DIR, "part803_adverse_events_*.csv.gz")
    if mau_path is not None:
        mau = pd.read_csv(mau_path, low_memory=False,
                          usecols=["device_report_product_code",
                                   "medical_specialty", "device_class"])
        pc = (mau["device_report_product_code"].astype(str)
              .str.strip().str.upper())
        hit = pc.isin(codes)
        print(f"    803 MAUDE    : {hit.sum():,} of {len(pc):,} records "
              f"resolved ({hit.mean():.1%}); "
              f"{pc.nunique():,} distinct codes")

        # Does the lookup actually RESOLVE MAUDE's missing specialties?
        #
        # It must not be enough for the lookup to return a non-null value:
        # FDA's own classification table carries the literal string 'Unknown'
        # for many product codes, so a bare notna() check scores those as
        # recoveries and reports ~100% success when the true figure is ~0%.
        # A specialty counts as resolved ONLY if it is a real category.
        spec = mau["medical_specialty"]
        unknown = spec.isna() | spec.astype(str).str.strip().eq("Unknown")
        good = lookup.set_index("product_code")["dev_medical_specialty_description"]
        mapped = pc.map(good)
        is_real = mapped.notna() & mapped.astype(str).str.strip().ne("Unknown")
        recovered = unknown & is_real
        print(f"    'Unknown' specialty in MAUDE : {unknown.sum():,} "
              f"({unknown.mean():.1%})")
        print(f"    ... genuinely resolved       : {recovered.sum():,} "
              f"({recovered.sum() / max(int(unknown.sum()), 1):.1%} of them) "
              f"- 'Unknown' in the lookup does NOT count")

        # Cross-check MAUDE's own device_class against the authoritative one.
        # Agreement is reported rather than assumed: if it is high, MAUDE's
        # field is trustworthy and the lookup's value-add lies elsewhere.
        if "device_class" not in mau.columns:
            return                       # nothing to cross-check against
        both = pd.to_numeric(mau["device_class"], errors="coerce")
        auth = pc.map(lookup.set_index("product_code")["dev_device_class_num"])
        comparable = both.notna() & auth.notna()
        if comparable.any():
            agree = (both[comparable] == auth[comparable]).mean()
            print(f"    device_class agreement       : {agree:.1%} "
                  f"on {int(comparable.sum()):,} comparable records")


# =============================================================
# STEP 4. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / f"fda_device_classification_{snapshot_date}.csv"
    out_path = PROCESSED_DIR / f"device_product_code_lookup_{snapshot_date}.csv"

    print("=" * 64)
    print("FDA Device Classification - product-code lookup")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 64)

    print("[1/4] Downloading device/classification ...")
    df = fetch_classification()
    df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"    raw ({len(df):,} rows) -> {raw_path.relative_to(REPO_ROOT)}")

    print("[2/4] Building product-code lookup ...")
    lookup = build_lookup(df)
    lookup.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    lookup ({len(lookup):,} codes) -> {out_path.relative_to(REPO_ROOT)}")

    print("[3/4] Coverage against the timeline datasets ...")
    if "--skip-coverage" in sys.argv:
        print("    skipped (--skip-coverage)")
    else:
        report_coverage(lookup)

    print("[4/4] Summary")
    cls = lookup["dev_device_class_num"].value_counts().sort_index()
    print("  device class (product codes, not records):")
    for k, v in cls.items():
        print(f"     Class {k}: {v:,} codes")
    for flag, label in [("dev_implant_flag_bool", "implantable"),
                        ("dev_life_sustain_support_flag_bool", "life-sustaining"),
                        ("dev_gmp_exempt_flag_bool", "GMP-exempt")]:
        if flag in lookup:
            print(f"  {label:<16}: {int(lookup[flag].sum()):,} codes")
    print(f"  distinct specialties: "
          f"{lookup['dev_medical_specialty_description'].nunique():,}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
