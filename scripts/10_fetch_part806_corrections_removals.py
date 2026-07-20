# =============================================================
# Script: 10_fetch_part806_corrections_removals.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Acquire the FULL HISTORY of medical-device CORRECTIONS AND REMOVALS
#          (21 CFR Part 806) from openFDA, and link them to the project's
#          gvkey-linked sample firms. This is the MIDDLE of the regulatory
#          timeline the project wants to reconstruct:
#
#              adverse event (Part 803)  ->  correction/removal (Part 806)
#                                        ->  warning letter (script 03)
#
# Sources: openFDA bulk downloads (public, no key required)
#   A. device/recall      - CDRH "Medical Device Recalls" (RES) database.
#                           ~58,700 records back to 2002. Carries
#                           firm_fei_number, root_cause_description, and the
#                           date the firm INITIATED the action.
#   B. device/enforcement - Recall Enforcement Reports. ~39,500 records.
#                           Carries the recall CLASSIFICATION (Class I/II/III)
#                           and voluntary-vs-mandated status. Covers a shorter
#                           window than (A), so it is attached as an OPTIONAL
#                           enrichment, never used to filter.
#
# ---------------------------------------------------------------------------
# MEASUREMENT CAVEAT (important for the paper - do not lose this):
#   The Part 806 reports firms file with FDA are NOT themselves public. What
#   is public is the RES recall database, i.e. the subset of corrections and
#   removals FDA classified and posted. Two consequences:
#     (1) This is a LOWER BOUND on 806 activity. Actions FDA never classified,
#         and market withdrawals / stock recoveries exempt from 806, are absent.
#     (2) Some records here arise under 21 CFR Part 7 (voluntary recall
#         guidance) rather than 806 proper. The `voluntary_mandated` field
#         from the enforcement file is the best available separator, and is
#         carried through to the processed output.
#   Treat the resulting variable as "publicly observable correction/removal
#   activity," not "Part 806 filings."
# ---------------------------------------------------------------------------
#
# Sample restriction (design decision, Ryan 2026-07-19; scope confirmed by RB):
#   RAW is universe-wide, PROCESSED is restricted to sample firms. The openFDA
#   bulk files are single monolithic partitions, so a "restricted download"
#   saves nothing - the whole file must be fetched either way. Keeping the raw
#   snapshot complete costs ~360 MB and means control-firm or spillover
#   analysis never requires a re-pull. Same philosophy as script 03.
#
# Inputs:  data/processed/fda_compliance_actions_<DATE>.csv                 (script 03)
#          data/processed/compliance_actions_gvkey_crosswalk_full_<DATE>.csv (script 05)
# Outputs: data/raw/fda_device_recalls_<DATE>.csv               (universe, untouched)
#          data/raw/fda_device_enforcement_<DATE>.csv           (universe, untouched)
#          data/processed/part806_corrections_removals_<DATE>.csv    (sample firms)
#          data/processed/part806_unlinked_device_firms_<DATE>.csv   (manual worklist)
#
# Usage:   python scripts/10_fetch_part806_corrections_removals.py
#          python scripts/10_fetch_part806_corrections_removals.py --use-cached
#              (skip re-downloading if today's raw snapshot already exists)
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import io
import json
import re
import sys
import glob
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# openFDA publishes a manifest of bulk-download URLs; we read it rather than
# hard-coding file paths, because the partition filenames change each release.
DOWNLOAD_MANIFEST = "https://api.fda.gov/download.json"

# Sanity floors: record counts on 2026-07-19. These datasets only grow, so a
# pull far below the floor signals a truncated download, not real data.
MIN_EXPECTED_RECALLS = 55_000
MIN_EXPECTED_ENFORCEMENT = 35_000

# Columns kept from each source. openFDA returns deeply nested JSON (the
# `openfda` block, product arrays); we keep the flat scalar fields that are
# populated consistently across the full history and drop the rest.
RECALL_COLUMNS = [
    "cfres_id", "res_event_number", "product_res_number",
    "firm_fei_number", "recalling_firm", "city", "state", "postal_code",
    "event_date_initiated", "event_date_posted", "event_date_terminated",
    "recall_status", "product_code", "k_numbers",
    "product_description", "reason_for_recall", "root_cause_description",
    "action", "distribution_pattern", "product_quantity",
]
ENFORCEMENT_COLUMNS = [
    "event_id", "recall_number", "classification", "voluntary_mandated",
    "status", "recalling_firm", "recall_initiation_date",
    "center_classification_date", "report_date",
    "initial_firm_notification", "product_description", "reason_for_recall",
]


# =============================================================
# STEP 1. Company-name normalization
# =============================================================
# Identical rules to scripts 02/04/05 (kept in sync BY HAND - if you edit one,
# edit the others). Reused here so that a recalling-firm name normalizes to the
# same key as the warning-letter recipient names already in the crosswalk.

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


def normalize_fei(raw) -> str:
    """
    Return an FEI as a comparison key. FEI numbers appear as floats in the
    Compustat-era CSVs ('1000139935.0'), as ints in the API, and occasionally
    zero-padded. Strip all three so the join is on the same token.
    """
    if pd.isna(raw):
        return ""
    s = str(raw).strip()
    s = re.sub(r"\.0+$", "", s)           # '1000139935.0' -> '1000139935'
    s = re.sub(r"[^0-9]", "", s)
    return s.lstrip("0")


# =============================================================
# STEP 2. Bulk download from openFDA
# =============================================================
def fetch_openfda_bulk(endpoint: str, min_expected: int) -> pd.DataFrame:
    """
    Download every partition of an openFDA bulk export and return it as a flat
    DataFrame.

    We use the BULK files rather than the paged API deliberately: the API caps
    `skip` at 25,000 records, which cannot reach the ~58,700 recall records.
    The bulk route also gives a stable, citable export_date.
    """
    manifest = requests.get(DOWNLOAD_MANIFEST, timeout=120).json()
    node = manifest["results"]["device"][endpoint]
    partitions = node["partitions"]
    print(f"    manifest: export_date={node['export_date']}, "
          f"{node['total_records']:,} records in {len(partitions)} partition(s)")

    records = []
    for i, part in enumerate(partitions, start=1):
        url = part["file"]
        print(f"    [{i}/{len(partitions)}] downloading {part['size_mb']} MB ...")
        resp = requests.get(url, timeout=600)
        resp.raise_for_status()
        # Each partition is a .json.zip containing one JSON file with a
        # top-level "results" array.
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            inner = zf.namelist()[0]
            with zf.open(inner) as fh:
                payload = json.load(fh)
        records.extend(payload.get("results", []))
        print(f"        cumulative records: {len(records):,}")

    if len(records) < min_expected:
        raise RuntimeError(
            f"Only {len(records):,} {endpoint} records retrieved "
            f"(expected >= {min_expected:,}). Download looks truncated.")

    return pd.json_normalize(records)


def keep_columns(df: pd.DataFrame, wanted: list) -> pd.DataFrame:
    """
    Subset to the wanted columns, tolerating any that openFDA drops in a given
    release. Missing columns are created empty rather than raising, so a schema
    change degrades the output instead of killing the pipeline - but it is
    reported loudly.
    """
    missing = [c for c in wanted if c not in df.columns]
    if missing:
        print(f"    NOTE: columns absent from this release: {missing}")
        for c in missing:
            df[c] = pd.NA
    return df[wanted].copy()


# =============================================================
# STEP 3. Build the sample-firm key sets (FEI and normalized name)
# =============================================================
def latest(pattern: str) -> Path:
    """Return the most recent date-stamped file matching a glob pattern."""
    hits = sorted(glob.glob(str(PROCESSED_DIR / pattern)))
    if not hits:
        raise FileNotFoundError(
            f"No file matches {pattern} in data/processed/. "
            "Run scripts 03-05 first.")
    return Path(hits[-1])


def build_sample_keys() -> tuple:
    """
    Assemble the two key sets that define "a sample firm" for this pull.

    Two independent routes, because neither alone is sufficient:

      Route A - FEI. The compliance-actions file (script 03) carries the FEI of
        the ESTABLISHMENT that received each letter. Joining those FEIs to the
        recall file is an EXACT establishment-level match - no name matching,
        no judgment calls. This is the highest-confidence link in the project.
        Limitation: it only sees establishments that actually received a
        letter, so a sample firm's other plants are invisible to it.

      Route B - normalized name. Matching the recalling firm's normalized name
        against the crosswalk recovers those other establishments, and firms
        that recalled but were never cited. Lower confidence, so every Route-B
        link is flagged as such in the output and can be dropped with one
        filter if a referee objects.

    Returns (fei_to_gvkey, name_to_gvkey, crosswalk) where the first two map a
    key to the gvkey/company metadata of the owning firm.
    """
    ca_path = latest("fda_compliance_actions_*.csv")
    cx_path = latest("compliance_actions_gvkey_crosswalk_full_*.csv")
    print(f"    compliance actions : {ca_path.name}")
    print(f"    crosswalk (full)   : {cx_path.name}")

    ca = pd.read_csv(ca_path, low_memory=False)
    cx = pd.read_csv(cx_path, low_memory=False)

    # Restrict the crosswalk to firms with a gvkey. Keep ALL product types:
    # a device recall at a firm we know from a drug letter is still a real
    # observation, and dropping it would bias the timeline sample toward firms
    # whose FIRST regulatory contact happened to be device-side.
    cx = cx[cx["gvkey"].notna()].copy()
    cx["gvkey"] = cx["gvkey"].astype("int64")
    cx["norm_key"] = cx["company_name_fda"].map(normalize_name)

    # --- Route B: normalized name -> firm metadata.
    # Where two crosswalk rows normalize to the same key (subsidiaries of the
    # same parent), they resolve to the same gvkey by construction, so keeping
    # the first is safe. Where they do NOT, the name is ambiguous and we drop
    # it rather than guess - consistent with script 04's precision-first rule.
    name_to_gvkey = {}
    ambiguous = set()
    for key, grp in cx.groupby("norm_key"):
        if not key:
            continue
        if grp["gvkey"].nunique() > 1:
            ambiguous.add(key)
            continue
        row = grp.iloc[0]
        name_to_gvkey[key] = {
            "gvkey": int(row["gvkey"]),
            "company_name_compustat": row["company_name_compustat"],
            "match_source_crosswalk": row["match_source"],
            "review_suggested": bool(row["review_suggested"]),
            "valid_from_year": int(row["valid_from_year"]),
            "valid_to_year": int(row["valid_to_year"]),
        }
    if ambiguous:
        print(f"    dropped {len(ambiguous)} ambiguous normalized names "
              f"(map to >1 gvkey)")

    # --- Route A: FEI -> firm metadata, via the letter recipient's name.
    ca["norm_key"] = ca["company_name_clean"].map(normalize_name)
    ca["fei_key"] = ca["FEI Number"].map(normalize_fei)
    linked = ca[ca["norm_key"].isin(name_to_gvkey) & ca["fei_key"].ne("")]

    fei_to_gvkey = {}
    for fei, grp in linked.groupby("fei_key"):
        # An FEI is an establishment; if letters at one establishment map to
        # different owners over time, ownership changed. Take the crosswalk
        # entry and let the ownership-window check in STEP 4 sort out timing.
        keys = grp["norm_key"].unique()
        if len({name_to_gvkey[k]["gvkey"] for k in keys}) > 1:
            continue  # ambiguous establishment ownership - skip, do not guess
        fei_to_gvkey[fei] = name_to_gvkey[keys[0]]

    print(f"    sample firms (gvkey)     : {cx['gvkey'].nunique():,}")
    print(f"    Route A keys (FEI)       : {len(fei_to_gvkey):,}")
    print(f"    Route B keys (norm name) : {len(name_to_gvkey):,}")
    return fei_to_gvkey, name_to_gvkey, cx


# =============================================================
# STEP 4. Link recalls to sample firms
# =============================================================
def link_recalls(recalls: pd.DataFrame, fei_to_gvkey: dict,
                 name_to_gvkey: dict) -> pd.DataFrame:
    """
    Attach firm identifiers to each recall record, preferring the exact FEI
    match and falling back to the normalized-name match. Ownership windows are
    enforced: a recall links to the firm that owned the establishment IN THE
    YEAR THE ACTION WAS INITIATED, which matters for the acquisition-heavy
    medtech sector (script 05 built those windows for exactly this reason).
    """
    out = recalls.copy()
    out["fei_key"] = out["firm_fei_number"].map(normalize_fei)
    out["norm_key"] = out["recalling_firm"].map(normalize_name)

    # Initiation date drives event time: it is when the FIRM acted, which is
    # the decision the paper is about. Posted date is FDA's administrative
    # timestamp and is used only as a fallback when initiation is missing.
    out["event_date_initiated"] = pd.to_datetime(
        out["event_date_initiated"], errors="coerce")
    out["event_date_posted"] = pd.to_datetime(
        out["event_date_posted"], errors="coerce")
    out["action_year"] = (out["event_date_initiated"]
                          .fillna(out["event_date_posted"]).dt.year)

    def resolve(row):
        """Return (meta, link_source) for one recall row, or (None, None)."""
        meta = fei_to_gvkey.get(row["fei_key"])
        source = "fei_exact"
        if meta is None:
            meta = name_to_gvkey.get(row["norm_key"])
            source = "name_normalized"
        if meta is None:
            return None, None
        # Enforce the ownership window.
        yr = row["action_year"]
        if pd.notna(yr) and not (meta["valid_from_year"] <= yr <= meta["valid_to_year"]):
            return None, None
        return meta, source

    resolved = out.apply(resolve, axis=1)
    out["link_source"] = [r[1] for r in resolved]
    for field in ["gvkey", "company_name_compustat", "match_source_crosswalk",
                  "review_suggested"]:
        out[field] = [r[0][field] if r[0] is not None else pd.NA
                      for r in resolved]

    linked = out[out["link_source"].notna()].copy()
    print(f"    linked recalls           : {len(linked):,} of {len(out):,}")
    print(f"       via FEI (exact)       : "
          f"{int((linked['link_source'] == 'fei_exact').sum()):,}")
    print(f"       via normalized name   : "
          f"{int((linked['link_source'] == 'name_normalized').sum()):,}")
    print(f"    distinct firms (gvkey)   : {linked['gvkey'].nunique():,}")
    return linked


def attach_classification(linked: pd.DataFrame,
                          enforcement: pd.DataFrame) -> pd.DataFrame:
    """
    Attach recall severity from the enforcement file.

    Join keys, in priority order (verified empirically 2026-07-19):
      1. product-level: recall.product_res_number == enforcement.recall_number
      2. event-level:   recall.res_event_number  == enforcement.event_id

    Enforcement reports begin later than the RES recall database, so pre-2012
    recalls legitimately have no classification. That is recorded as missing,
    NOT dropped - dropping would silently truncate the sample's early years.
    """
    enf = enforcement.copy()
    enf["recall_number"] = enf["recall_number"].astype(str).str.strip()
    enf["event_id"] = enf["event_id"].astype(str).str.strip()

    # --- 1. Product-level join (exact, one-to-one).
    prod = (enf.drop_duplicates("recall_number")
               .set_index("recall_number")[["classification",
                                            "voluntary_mandated",
                                            "recall_initiation_date",
                                            "center_classification_date",
                                            "initial_firm_notification"]])
    out = linked.copy()
    out["_rn"] = out["product_res_number"].astype(str).str.strip()
    out = out.join(prod, on="_rn")

    # --- 2. Event-level backfill for rows the product join missed.
    evt = (enf.drop_duplicates("event_id")
              .set_index("event_id")[["classification", "voluntary_mandated"]]
              .rename(columns={"classification": "_cls_evt",
                               "voluntary_mandated": "_vol_evt"}))
    out["_ev"] = out["res_event_number"].astype(str).str.strip()
    out = out.join(evt, on="_ev")
    out["classification"] = out["classification"].fillna(out["_cls_evt"])
    out["voluntary_mandated"] = out["voluntary_mandated"].fillna(out["_vol_evt"])
    out = out.drop(columns=["_rn", "_ev", "_cls_evt", "_vol_evt"])

    n_class = int(out["classification"].notna().sum())
    print(f"    classification attached  : {n_class:,} of {len(out):,} "
          f"({n_class / max(len(out), 1):.1%})")
    if n_class:
        for cls, n in out["classification"].value_counts().items():
            print(f"       {cls:<12}: {n:,}")
    return out


# =============================================================
# STEP 5. Unlinked worklist
# =============================================================
def build_unlinked_worklist(recalls: pd.DataFrame,
                            linked: pd.DataFrame) -> pd.DataFrame:
    """
    Recalling firms we could NOT link, ranked by recall count.

    Most are genuinely private or foreign manufacturers with no Compustat
    record - a low link rate is the honest outcome here, exactly as it was for
    the warning letters (script 04's philosophy). But the top of this list is
    where a few hours of manual review buys the most sample, so it is written
    out sorted by volume.
    """
    unlinked = recalls[~recalls.index.isin(linked.index)].copy()
    work = (unlinked.groupby("recalling_firm")
            .agg(n_recalls=("cfres_id", "size"),
                 n_fei=("firm_fei_number", "nunique"),
                 first_action=("event_date_initiated", "min"),
                 last_action=("event_date_initiated", "max"))
            .reset_index()
            .sort_values("n_recalls", ascending=False))
    work["normalized_name"] = work["recalling_firm"].map(normalize_name)
    return work


# =============================================================
# STEP 6. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    use_cached = "--use-cached" in sys.argv
    raw_recall_path = RAW_DIR / f"fda_device_recalls_{snapshot_date}.csv"
    raw_enf_path = RAW_DIR / f"fda_device_enforcement_{snapshot_date}.csv"
    out_path = PROCESSED_DIR / f"part806_corrections_removals_{snapshot_date}.csv"
    work_path = PROCESSED_DIR / f"part806_unlinked_device_firms_{snapshot_date}.csv"

    print("=" * 64)
    print("FDA Part 806 - Corrections & Removals (device recalls)")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 64)

    # --- 6a. Acquire (universe-wide; raw is sacred). ---
    if use_cached and raw_recall_path.exists() and raw_enf_path.exists():
        print("[1/5] Using cached raw snapshots (--use-cached) ...")
        recalls = pd.read_csv(raw_recall_path, low_memory=False)
        enforcement = pd.read_csv(raw_enf_path, low_memory=False)
    else:
        print("[1/5] Downloading device/recall bulk export ...")
        recalls = keep_columns(
            fetch_openfda_bulk("recall", MIN_EXPECTED_RECALLS), RECALL_COLUMNS)
        recalls.to_csv(raw_recall_path, index=False, encoding="utf-8-sig")
        print(f"    raw -> {raw_recall_path.relative_to(REPO_ROOT)}")

        print("    Downloading device/enforcement bulk export ...")
        enforcement = keep_columns(
            fetch_openfda_bulk("enforcement", MIN_EXPECTED_ENFORCEMENT),
            ENFORCEMENT_COLUMNS)
        enforcement.to_csv(raw_enf_path, index=False, encoding="utf-8-sig")
        print(f"    raw -> {raw_enf_path.relative_to(REPO_ROOT)}")

    print(f"    recalls: {len(recalls):,} | enforcement: {len(enforcement):,}")

    # --- 6b. Sample keys. ---
    print("[2/5] Building sample-firm key sets ...")
    fei_to_gvkey, name_to_gvkey, _ = build_sample_keys()

    # --- 6c. Link. ---
    print("[3/5] Linking recalls to sample firms ...")
    linked = link_recalls(recalls, fei_to_gvkey, name_to_gvkey)

    # --- 6d. Enrich with severity. ---
    print("[4/5] Attaching recall classification ...")
    linked = attach_classification(linked, enforcement)
    linked.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    processed -> {out_path.relative_to(REPO_ROOT)}")

    work = build_unlinked_worklist(recalls, linked)
    work.to_csv(work_path, index=False, encoding="utf-8-sig")
    print(f"    worklist  -> {work_path.relative_to(REPO_ROOT)} "
          f"({len(work):,} unlinked firms)")

    # --- 6e. Summary. ---
    print("[5/5] Summary")
    dates = linked["event_date_initiated"].dropna()
    if len(dates):
        print(f"  action-initiated range : {dates.min().date()} to {dates.max().date()}")
    print(f"  linked recall records  : {len(linked):,}")
    print(f"  distinct firms (gvkey) : {linked['gvkey'].nunique():,}")
    print(f"  distinct FEIs          : {linked['fei_key'].nunique():,}")
    print("  top firms by recall count:")
    top = linked.groupby("company_name_compustat").size().nlargest(10)
    for name, n in top.items():
        print(f"     {str(name)[:38]:<40} {n:,}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
