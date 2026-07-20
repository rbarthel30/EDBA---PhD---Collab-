# =============================================================
# Script: 12_link_fda_firm_names_to_gvkey.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: GENERALIZED FDA-firm-name -> Compustat gvkey matcher. Takes firm
#          names from ANY FDA source (recall/Part 806, MAUDE/Part 803, warning
#          letters) and links them to gvkey by matching against the FULL
#          Compustat company master - INDEPENDENT of the warning-letter data.
#
# ---------------------------------------------------------------------------
# WHY THIS EXISTS (the sample-selection problem it fixes):
#
#   Script 10 linked recalls to firms two ways: an FEI bridge borrowed from the
#   warning-letter file, and a name match against the letter-derived crosswalk.
#   Both routes are CONDITIONED ON HAVING RECEIVED A LETTER:
#
#     * The FEI bridge only resolves at facilities that received a letter -
#       definitionally treated firms.
#     * The crosswalk from scripts 04/05 is a dictionary of LETTER RECIPIENT
#       names, so it matches recall-side names poorly by construction.
#
#   Net effect: the 806 linkage can only ever find recalls at firms already in
#   the letter sample (67 of 113 linked firms were reachable ONLY via the FEI
#   bridge). That is fine for enriching treated firms and FATAL for expanding
#   the sample or building a control group.
#
#   This script breaks that dependence. It matches FDA firm names straight to
#   Compustat, so a device firm with recalls or adverse events but NO warning
#   letter can enter the sample. Those firms are the natural control group the
#   disclosure hypotheses need, and right now they structurally cannot exist.
# ---------------------------------------------------------------------------
#
# MATCHING PHILOSOPHY (inherited from script 04 - precision over recall):
#   * Normalize both sides (uppercase, strip punctuation and corporate forms).
#   * Accept a link ONLY when a normalized name maps to EXACTLY ONE gvkey.
#     Names hitting several gvkeys are recorded as ambiguous and DROPPED, not
#     resolved by a tiebreak.
#   * SIC GATE = DEVICE OR PHARMA/BIO ONLY (3841-3845, 2833-2836). Matches
#     landing outside those ranges are rejected. Rationale: exact name
#     matching cannot catch a genuine NAME COLLISION between an FDA-regulated
#     firm and an unrelated Compustat firm of the same name - the validation
#     spot-check found 'IMTEC Corporation' (dental implants) matching an
#     'IMTEC INC' in SIC 5110 (paper wholesale). Collisions concentrate almost
#     entirely in the out-of-industry bucket, so gating on industry removes
#     them cheaply.
#     NOTE the gate deliberately spans BOTH ranges: restricting to device SIC
#     alone would drop the largest device makers, since Abbott, J&J and
#     Medtronic are classified in pharma codes.
#   * Cross-entity-family matches (e.g. FDA 'X Ltd' vs Compustat 'X Inc') are
#     kept but FLAGGED, since they are a common source of false positives
#     between a foreign parent and an unrelated domestic firm.
#
# KNOWN LIMITATION - HISTORICAL NAMES:
#   comp.company carries only each firm's CURRENT name. A firm that renamed or
#   was acquired will not match its historical FDA-era name (a 2010 recall by
#   'Guidant' will not match Compustat's 'Boston Scientific'). This script
#   therefore UNDER-matches older records. The hand-curated subsidiary
#   crosswalks used by script 05 exist precisely to patch this, and are merged
#   in at STEP 6 rather than duplicated here.
#
# Inputs:  data/raw/compustat_company_<DATE>.csv                   (cached; or WRDS)
#          data/raw/fda_device_recalls_<DATE>.csv                  (script 10)
#          data/processed/part803_adverse_events_<DATE>.csv.gz     (script 11, optional)
#          data/processed/compliance_actions_gvkey_crosswalk_full_<DATE>.csv (script 05)
# Outputs: data/processed/fda_firm_gvkey_crosswalk_unified_<DATE>.csv
#          data/processed/fda_firm_unmatched_worklist_<DATE>.csv
#          data/processed/fda_firm_ambiguous_names_<DATE>.csv
#
# Usage:   python scripts/12_link_fda_firm_names_to_gvkey.py
#          python scripts/12_link_fda_firm_names_to_gvkey.py --refresh-compustat
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import os
import re
import sys
import glob
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

WRDS_USERNAME = os.environ.get("WRDS_USERNAME", "rxb1406")

# A normalized name shorter than this is too generic to match safely
# ('BD', 'ACE', 'CARE'). Such names are routed to the worklist instead.
MIN_SAFE_NAME_LEN = 5

# Industry gate for accepting a Compustat match (see MATCHING PHILOSOPHY).
# A match outside these SIC ranges is recorded as 'out_of_industry' and
# excluded from the crosswalk, rather than accepted and flagged.
DEVICE_SIC = (3841, 3845)      # surgical/medical instruments, in-vitro, etc.
PHARMA_BIO_SIC = (2833, 2836)  # pharma preparations, biologics


def in_scope_sic(sic) -> bool:
    """True if a Compustat SIC falls in the device or pharma/bio ranges."""
    if pd.isna(sic):
        return False
    s = int(sic)
    return (DEVICE_SIC[0] <= s <= DEVICE_SIC[1]
            or PHARMA_BIO_SIC[0] <= s <= PHARMA_BIO_SIC[1])


# =============================================================
# STEP 1. Company-name normalization
# =============================================================
# Identical rules to scripts 02/04/05/10/11 (kept in sync BY HAND - if you edit
# one, edit the others).

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
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(_SUFFIX_RE, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def entity_family(raw: str) -> str:
    """Classify a name's corporate form as 'domestic', 'foreign', or 'none'."""
    tokens = set(re.sub(r"[^A-Z ]", " ", str(raw).upper()).split())
    if tokens & FOREIGN_FORMS:
        return "foreign"
    if tokens & DOMESTIC_FORMS:
        return "domestic"
    return "none"


def latest(directory: Path, pattern: str, required: bool = True):
    """Return the most recent date-stamped file matching a glob pattern."""
    hits = sorted(glob.glob(str(directory / pattern)))
    if not hits:
        if required:
            raise FileNotFoundError(
                f"No file matches {pattern} in {directory.name}/.")
        return None
    return Path(hits[-1])


# =============================================================
# STEP 2. Load the Compustat company master
# =============================================================
def load_compustat(refresh: bool) -> pd.DataFrame:
    """
    Load comp.company. Prefers the cached raw pull from script 04 so this
    script runs without WRDS credentials; --refresh-compustat forces a new
    pull (the licensed extract stays gitignored either way).
    """
    if not refresh:
        cached = latest(RAW_DIR, "compustat_company_*.csv", required=False)
        if cached is not None:
            print(f"    using cached Compustat master: {cached.name}")
            return pd.read_csv(cached, low_memory=False)

    print(f"    connecting to WRDS as '{WRDS_USERNAME}' ...")
    import wrds  # imported lazily so the cached path needs no WRDS install
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        company = db.raw_sql(
            "select gvkey, conm, conml, cik, sic, naics, costat "
            "from comp.company")
    finally:
        db.close()
    out_path = RAW_DIR / f"compustat_company_{date.today().isoformat()}.csv"
    company.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    pulled {len(company):,} firms -> {out_path.relative_to(REPO_ROOT)}")
    return company


def build_compustat_index(company: pd.DataFrame) -> tuple:
    """
    Build normalized-name -> gvkey lookup from the Compustat master.

    Both `conm` (the short/CRSP-style name) and `conml` (the long legal name)
    are indexed: FDA sources sometimes carry the trading name and sometimes the
    full legal entity, and indexing only one loses matches on the other.

    A normalized name resolving to more than one gvkey is AMBIGUOUS and is
    excluded from the lookup entirely - returned separately so the ambiguity is
    visible and auditable rather than silently resolved.
    """
    name_to_gvkeys = defaultdict(set)
    meta = {}
    for row in company.itertuples(index=False):
        gv = int(row.gvkey)
        for raw in (row.conm, row.conml):
            if pd.isna(raw):
                continue
            key = normalize_name(raw)
            if len(key) < MIN_SAFE_NAME_LEN:
                continue
            name_to_gvkeys[key].add(gv)
            meta.setdefault(gv, {
                "gvkey": gv,
                "company_name_compustat": row.conm,
                "sic": row.sic,
                "costat": row.costat,
                "cik": row.cik,
                "compustat_entity_family": entity_family(raw),
            })

    lookup = {k: meta[next(iter(v))] for k, v in name_to_gvkeys.items()
              if len(v) == 1}
    ambiguous = {k: sorted(v) for k, v in name_to_gvkeys.items() if len(v) > 1}
    print(f"    Compustat firms indexed  : {len(meta):,}")
    print(f"    unique normalized names  : {len(lookup):,} usable, "
          f"{len(ambiguous):,} ambiguous (dropped)")
    return lookup, ambiguous


# =============================================================
# STEP 3. Harvest distinct firm names from each FDA source
# =============================================================
def harvest_source_names() -> pd.DataFrame:
    """
    Collect distinct firm names from every available FDA source, with the
    record volume behind each name.

    Volume matters: it is what makes the unmatched worklist actionable. A name
    attached to 400 recalls is worth ten minutes of manual review; one attached
    to a single report is not.
    """
    frames = []

    # --- 3a. Part 806 recalls (universe-wide raw, NOT the sample-restricted
    # processed file - the whole point is to reach beyond the letter sample).
    rec_path = latest(RAW_DIR, "fda_device_recalls_*.csv", required=False)
    if rec_path is not None:
        rec = pd.read_csv(rec_path, low_memory=False)
        g = (rec.groupby("recalling_firm").size()
             .reset_index(name="n_records"))
        g["source"] = "part806_recall"
        g = g.rename(columns={"recalling_firm": "firm_name_fda"})
        frames.append(g)
        print(f"    part806 recalls : {len(g):,} distinct firm names "
              f"({len(rec):,} records)")
    else:
        print("    part806 recalls : SKIPPED (run script 10 first)")

    # --- 3b. Part 803 MAUDE (optional - script 11 is long-running).
    mau_path = latest(PROCESSED_DIR, "part803_adverse_events_*.csv.gz",
                      required=False)
    if mau_path is not None:
        mau = pd.read_csv(mau_path, low_memory=False,
                          usecols=["manufacturer_d_name"])
        g = (mau.groupby("manufacturer_d_name").size()
             .reset_index(name="n_records"))
        g["source"] = "part803_maude"
        g = g.rename(columns={"manufacturer_d_name": "firm_name_fda"})
        frames.append(g)
        print(f"    part803 MAUDE   : {len(g):,} distinct firm names "
              f"({len(mau):,} records)")
    else:
        print("    part803 MAUDE   : SKIPPED (script 11 output not present yet)")

    # --- 3c. MAUDE names that script 11 could NOT link. This is where the
    # unmatched sample is hiding, so it is fed in explicitly.
    unm_path = latest(PROCESSED_DIR, "part803_unmatched_manufacturers_*.csv",
                      required=False)
    if unm_path is not None:
        unm = pd.read_csv(unm_path)
        g = unm.rename(columns={"normalized_manufacturer": "firm_name_fda",
                                "n_reports": "n_records"})
        g["source"] = "part803_unmatched"
        frames.append(g[["firm_name_fda", "n_records", "source"]])
        print(f"    part803 unmatched: {len(g):,} distinct firm names")

    if not frames:
        raise RuntimeError("No FDA source files found. Run scripts 10/11 first.")

    out = pd.concat(frames, ignore_index=True)
    out = out[out["firm_name_fda"].notna()].copy()
    return out


# =============================================================
# STEP 4. Match FDA names to Compustat
# =============================================================
def match_to_compustat(names: pd.DataFrame, lookup: dict,
                       ambiguous: dict) -> pd.DataFrame:
    """
    Attach a gvkey to each distinct FDA firm name.

    Every row is labelled with `match_status` so that nothing is silently
    dropped and the sample can be reconstructed at any confidence level:
      matched          - exactly one Compustat gvkey
      ambiguous        - the name maps to several gvkeys; NOT resolved
      too_short        - normalized name below the safe-length floor
      unmatched        - no Compustat firm (usually genuinely private/foreign)
    """
    rows = []
    for r in names.itertuples(index=False):
        key = normalize_name(r.firm_name_fda)
        base = {
            "firm_name_fda": r.firm_name_fda,
            "normalized_name": key,
            "source": r.source,
            "n_records": r.n_records,
        }
        if not key or len(key) < MIN_SAFE_NAME_LEN:
            rows.append({**base, "match_status": "too_short"})
            continue
        if key in ambiguous:
            rows.append({**base, "match_status": "ambiguous",
                         "n_gvkey_candidates": len(ambiguous[key])})
            continue
        hit = lookup.get(key)
        if hit is None:
            rows.append({**base, "match_status": "unmatched"})
            continue
        # Industry gate: reject an otherwise-exact match that lands outside
        # device or pharma/bio. These are recorded (not discarded) so the
        # rejections stay auditable and can be reviewed by hand.
        if not in_scope_sic(hit["sic"]):
            rows.append({**base, "match_status": "out_of_industry",
                         "gvkey": hit["gvkey"],
                         "company_name_compustat": hit["company_name_compustat"],
                         "sic": hit["sic"]})
            continue
        # Flag cross-family matches (foreign FDA name vs domestic Compustat
        # name or vice versa) - a common false-positive pattern.
        fam_fda = entity_family(r.firm_name_fda)
        rows.append({
            **base,
            "match_status": "matched",
            "n_gvkey_candidates": 1,
            "gvkey": hit["gvkey"],
            "company_name_compustat": hit["company_name_compustat"],
            "sic": hit["sic"],
            "costat": hit["costat"],
            "cik": hit["cik"],
            "cross_entity_family": (
                fam_fda != "none"
                and hit["compustat_entity_family"] != "none"
                and fam_fda != hit["compustat_entity_family"]),
        })
    return pd.DataFrame(rows)


# =============================================================
# STEP 5. Merge with the existing letter-derived crosswalk
# =============================================================
def merge_with_letter_crosswalk(matched: pd.DataFrame) -> pd.DataFrame:
    """
    Union this script's Compustat matches with the hand-curated letter
    crosswalk from script 05.

    The letter crosswalk is NOT redundant: it carries subsidiary->parent links
    and ownership windows that a current-name Compustat match cannot recover
    (see the historical-names limitation in the header). Where both sources
    cover a name, the LETTER CROSSWALK WINS, because its subsidiary mappings
    were hand-validated and its ownership windows are the ones downstream
    joins rely on.
    """
    cx_path = latest(PROCESSED_DIR,
                     "compliance_actions_gvkey_crosswalk_full_*.csv",
                     required=False)
    if cx_path is None:
        print("    no letter crosswalk found - returning Compustat matches only")
        matched["crosswalk_origin"] = "compustat_direct"
        return matched

    cx = pd.read_csv(cx_path, low_memory=False)
    cx = cx[cx["gvkey"].notna()].copy()
    cx["normalized_name"] = cx["company_name_fda"].map(normalize_name)
    cx["crosswalk_origin"] = "letter_crosswalk"

    keep = ["normalized_name", "firm_name_fda", "gvkey",
            "company_name_compustat", "match_source", "review_suggested",
            "valid_from_year", "valid_to_year", "crosswalk_origin"]
    cx = cx.rename(columns={"company_name_fda": "firm_name_fda"})
    cx = cx[[c for c in keep if c in cx.columns]]

    ok = matched[matched["match_status"] == "matched"].copy()
    ok["crosswalk_origin"] = "compustat_direct"
    # Ownership windows are unknown for a direct current-name match, so they
    # are left wide open rather than invented. Downstream joins that need a
    # real window should prefer letter-crosswalk rows.
    ok["valid_from_year"] = 1900
    ok["valid_to_year"] = 2099
    ok["match_source"] = "compustat_exact"
    # Build the flag from a clean boolean series: the source column is object
    # dtype (it carries NaN for non-matched rows), and .fillna() on object
    # dtype is deprecated behaviour in pandas.
    ok["review_suggested"] = (ok["cross_entity_family"]
                              .astype("boolean").fillna(False).astype(bool))

    # The same firm name is harvested from several sources (a recall firm that
    # also appears in MAUDE), so collapse to one row per normalized name and
    # keep the TOTAL record volume behind it - that total is what makes the
    # downstream worklist prioritization meaningful.
    ok["n_records"] = ok.groupby("normalized_name")["n_records"].transform("sum")
    ok = ok.drop_duplicates("normalized_name", keep="first")

    unified = pd.concat([cx, ok], ignore_index=True)
    before = len(unified)
    unified = unified.sort_values(
        "crosswalk_origin",  # 'compustat_direct' < 'letter_crosswalk'
        ascending=False).drop_duplicates("normalized_name", keep="first")
    print(f"    unified crosswalk: {len(unified):,} names "
          f"({before - len(unified):,} duplicates resolved in favour of the "
          f"letter crosswalk)")
    return unified


# =============================================================
# STEP 6. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    refresh = "--refresh-compustat" in sys.argv

    print("=" * 64)
    print("Generalized FDA firm-name -> Compustat gvkey matcher")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 64)

    print("[1/5] Loading Compustat company master ...")
    company = load_compustat(refresh)
    lookup, ambiguous = build_compustat_index(company)

    print("[2/5] Harvesting firm names from FDA sources ...")
    names = harvest_source_names()
    print(f"    total name-source rows: {len(names):,}")

    print("[3/5] Matching to Compustat ...")
    matched = match_to_compustat(names, lookup, ambiguous)
    for status, n in matched["match_status"].value_counts().items():
        share = n / len(matched)
        print(f"    {status:<12}: {n:>7,} ({share:.1%})")

    print("[4/5] Merging with the letter-derived crosswalk ...")
    unified = merge_with_letter_crosswalk(matched)

    out_path = PROCESSED_DIR / f"fda_firm_gvkey_crosswalk_unified_{snapshot_date}.csv"
    work_path = PROCESSED_DIR / f"fda_firm_unmatched_worklist_{snapshot_date}.csv"
    amb_path = PROCESSED_DIR / f"fda_firm_ambiguous_names_{snapshot_date}.csv"

    unified.to_csv(out_path, index=False, encoding="utf-8-sig")
    (matched[matched["match_status"] == "unmatched"]
     .sort_values("n_records", ascending=False)
     .to_csv(work_path, index=False, encoding="utf-8-sig"))
    (matched[matched["match_status"] == "ambiguous"]
     .sort_values("n_records", ascending=False)
     .to_csv(amb_path, index=False, encoding="utf-8-sig"))
    # Audit trail for the industry gate: names that matched Compustat exactly
    # but were rejected on SIC. Reviewing this file is how you would catch a
    # real medtech firm misclassified into an out-of-scope SIC code.
    oos_path = PROCESSED_DIR / f"fda_firm_out_of_industry_{snapshot_date}.csv"
    (matched[matched["match_status"] == "out_of_industry"]
     .sort_values("n_records", ascending=False)
     .to_csv(oos_path, index=False, encoding="utf-8-sig"))
    print(f"    SIC-rejected -> {oos_path.relative_to(REPO_ROOT)}")

    print(f"    crosswalk -> {out_path.relative_to(REPO_ROOT)}")
    print(f"    worklist  -> {work_path.relative_to(REPO_ROOT)}")
    print(f"    ambiguous -> {amb_path.relative_to(REPO_ROOT)}")

    # --- 6a. The number that matters: how much did the sample actually grow? ---
    print("[5/5] Sample expansion")
    cx_path = latest(PROCESSED_DIR,
                     "compliance_actions_gvkey_crosswalk_full_*.csv",
                     required=False)
    letter_gvkeys = set()
    if cx_path is not None:
        cxx = pd.read_csv(cx_path, low_memory=False)
        letter_gvkeys = set(cxx.loc[cxx["gvkey"].notna(), "gvkey"].astype(int))

    new_gvkeys = set(unified.loc[unified["gvkey"].notna(), "gvkey"].astype(int))
    added = new_gvkeys - letter_gvkeys
    print(f"  firms in letter crosswalk        : {len(letter_gvkeys):,}")
    print(f"  firms in unified crosswalk       : {len(new_gvkeys):,}")
    print(f"  NEW firms (no warning letter)    : {len(added):,}  "
          f"<- the potential control group")

    if added:
        dev = company[company["gvkey"].isin(added)
                      & company["sic"].between(3841, 3845)]
        print(f"     of which SIC 3841-3845        : {len(dev):,}")
        print("  largest new firms by record volume:")
        # Map rather than merge: `unified` already carries an n_records column
        # from the Compustat-matched rows, so a merge would collide into
        # n_records_x / n_records_y and silently break this block.
        vol = (matched[matched["match_status"] == "matched"]
               .groupby("normalized_name")["n_records"].sum())
        top = unified[unified["gvkey"].isin(added)].copy()
        top["record_volume"] = top["normalized_name"].map(vol)
        top = (top.sort_values("record_volume", ascending=False)
                  .drop_duplicates("gvkey").head(10))
        for r in top.itertuples(index=False):
            n = r.record_volume
            label = "n/a" if pd.isna(n) else f"{int(n):,} records"
            print(f"     {str(r.company_name_compustat)[:38]:<40} {label}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
