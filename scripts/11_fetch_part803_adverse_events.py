# =============================================================
# Script: 11_fetch_part803_adverse_events.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Acquire medical-device ADVERSE EVENT REPORTS (21 CFR Part 803,
#          Medical Device Reporting) from openFDA/MAUDE, restricted to the
#          project's gvkey-linked sample firms. This is the FIRST stage of the
#          regulatory timeline:
#
#              adverse event (THIS SCRIPT)  ->  correction/removal (script 10)
#                                           ->  warning letter (script 03)
#
# Source:  openFDA device/event (MAUDE) bulk export - ~25.4 million reports
#          across ~362 quarterly partitions, 1991 to present.
#
# ---------------------------------------------------------------------------
# WHY BULK-STREAM RATHER THAN THE API (design decision, Ryan 2026-07-19):
#   The obvious route - query the API per firm - is not viable. openFDA allows
#   1,000 requests/day without an authorization key, and a firm-restricted pull
#   needs 10,000+ requests (300+ name variants x 25 years, plus pagination
#   around the 25,000-record `skip` ceiling). That is ~10 days of wall clock.
#
#   Instead we STREAM the bulk partitions: download one partition, keep only
#   records whose manufacturer matches a sample firm, discard the rest, move
#   on. No rate limit, no key, full record detail, and peak disk stays ~100 MB
#   instead of the 18 GB the complete archive would require.
#
#   Consequence, stated plainly: unlike script 10, this script does NOT keep a
#   universe-wide raw snapshot - 18 GB is not a reasonable thing to park in
#   data/raw/. Reproducibility is preserved instead by recording the openFDA
#   export_date and the exact partition list in a manifest written alongside
#   the output. Re-running against the same manifest reproduces the pull.
# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
# MEASUREMENT CAVEATS (important for the paper - do not lose these):
#   (1) MAUDE CARRIES NO FEI NUMBER. Unlike the recall data in script 10, there
#       is no establishment identifier to join on. Firms are identified only by
#       the free-text `device.manufacturer_d_name`. Linking is therefore NAME
#       MATCHING, with all the under-capture that implies. Every link is
#       flagged with its route so the strict subset can be isolated.
#   (2) MDR COUNTS ARE NOT INJURY COUNTS. Reporting propensity varies with
#       device type, firm reporting practice, litigation exposure, and FDA
#       attention - which is itself endogenous to receiving a warning letter.
#       A post-letter rise in MDRs may reflect reporting behavior, not device
#       performance. Any specification using MDR counts as an outcome needs to
#       address this directly.
#   (3) SUMMARY REPORTING changes over time. FDA's Alternative Summary
#       Reporting program (through 2019) let some manufacturers file bundled
#       reports, so pre-2019 counts understate events for affected devices.
#       The 2019 retirement of that program mechanically raises counts. Do not
#       read that break as a real change in device safety.
#   (4) Narrative text (`mdr_text`) is DROPPED to keep the output tractable.
#       It is the largest part of each record. Re-run with --keep-text if
#       text analysis is ever wanted.
# ---------------------------------------------------------------------------
#
# Inputs:  data/processed/compliance_actions_gvkey_crosswalk_full_<DATE>.csv (script 05)
# Outputs: data/processed/part803_adverse_events_<DATE>.csv.gz     (sample firms)
#          data/processed/part803_manifest_<DATE>.json             (reproducibility)
#          data/processed/part803_unmatched_manufacturers_<DATE>.csv (worklist)
#
# Usage:   python scripts/11_fetch_part803_adverse_events.py
#          python scripts/11_fetch_part803_adverse_events.py --since 2005
#          python scripts/11_fetch_part803_adverse_events.py --keep-text
#          python scripts/11_fetch_part803_adverse_events.py --resume
#
# RUNTIME: expect 2-5 hours. Progress prints per partition; --resume picks up
#          where an interrupted run stopped.
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import io
import gc
import os
import re
import sys
import glob
import json
import time
import gzip
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# Streaming cache location.
#
# DELIBERATELY OUTSIDE THE REPO. The repo lives under OneDrive, so anything
# written inside it syncs to university cloud storage. The cache is ~442 MB
# across 362 files of PURE DERIVED DATA - it carries no information beyond
# rebuild speed, so syncing and backing it up is wasted quota and sync churn.
# Keeping it, though, is worth it: with the cache a rebuild is ~1 minute;
# without it, an 18 GB download and ~50 minutes.
#
# Override with PART803_CACHE_DIR if you want it somewhere specific (e.g. a
# scratch volume, or a shared location when replicating on another machine).
_default_cache = (Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
                  / "edba_fda_cache" / "part803_stream")
CACHE_DIR = Path(os.environ.get("PART803_CACHE_DIR", _default_cache))

DOWNLOAD_MANIFEST = "https://api.fda.gov/download.json"

# Sanity floor: the archive held ~25.4M reports on 2026-07-19 and only grows.
MIN_EXPECTED_TOTAL = 20_000_000

# Flat scalar fields kept from the top level of each MDR record. Chosen for
# event-time analysis: when the event happened, when it reached FDA, what kind
# of event it was, and who reported it.
EVENT_FIELDS = [
    "report_number", "event_key", "mdr_report_key",
    "date_of_event", "date_received", "date_report",
    "date_report_to_fda", "date_facility_aware", "date_added", "date_changed",
    "event_type", "adverse_event_flag", "product_problem_flag",
    "report_source_code", "reporter_occupation_code", "health_professional",
    "initial_report_to_fda", "event_location", "number_devices_in_event",
    "number_patients_in_event", "manufacturer_name", "manufacturer_g1_name",
    "manufacturer_city", "manufacturer_state", "manufacturer_country",
    "remedial_action", "removal_correction_number",
]

# Device-level fields are pulled from the FIRST device entry on each report
# (MDRs can list several; the first is the subject device by MAUDE
# convention). They are selected explicitly in flatten_record() below, because
# several of them live inside the nested `openfda` block rather than at the
# device root.


# =============================================================
# STEP 1. Company-name normalization
# =============================================================
# Identical rules to scripts 02/04/05/10 (kept in sync BY HAND - if you edit
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


# =============================================================
# STEP 2. Build the sample-firm name index
# =============================================================
def latest(pattern: str) -> Path:
    """Return the most recent date-stamped file matching a glob pattern."""
    hits = sorted(glob.glob(str(PROCESSED_DIR / pattern)))
    if not hits:
        raise FileNotFoundError(
            f"No file matches {pattern} in data/processed/. Run scripts 03-05 first.")
    return Path(hits[-1])


def build_name_index() -> tuple:
    """
    Build the lookup that decides whether an MDR belongs to a sample firm.

    TWO TIERS, mirroring script 05's tiered philosophy:

      Tier A - EXACT normalized match. The manufacturer name on the MDR
        normalizes to exactly the same key as a crosswalk name (either the FDA
        recipient name or the Compustat name). High confidence; this is the
        default analysis sample.

      Tier B - PARENT PREFIX. The manufacturer name STARTS WITH a sample
        firm's normalized name, e.g. 'MEDTRONIC NEUROMODULATION' under
        'MEDTRONIC'. This is how MAUDE actually records divisions, so it
        recovers a lot - but it also risks false positives from unrelated
        firms sharing a leading token. Tier B rows are KEPT and FLAGGED
        (`link_tier`), never silently merged, so they can be included or
        excluded with a single filter.

    Prefix matching is restricted to keys of >= MIN_PREFIX_LEN characters, so
    short generic names ('COOK', 'BD') do not sweep in unrelated firms.
    """
    cx_path = latest("compliance_actions_gvkey_crosswalk_full_*.csv")
    print(f"    crosswalk: {cx_path.name}")
    cx = pd.read_csv(cx_path, low_memory=False)
    cx = cx[cx["gvkey"].notna()].copy()
    cx["gvkey"] = cx["gvkey"].astype("int64")

    exact, prefix_keys = {}, []
    ambiguous = set()
    for _, row in cx.iterrows():
        meta = {
            "gvkey": int(row["gvkey"]),
            "company_name_compustat": row["company_name_compustat"],
            "match_source_crosswalk": row["match_source"],
            "review_suggested": bool(row["review_suggested"]),
            "valid_from_year": int(row["valid_from_year"]),
            "valid_to_year": int(row["valid_to_year"]),
        }
        # Index BOTH the FDA-side name and the Compustat name: MAUDE sometimes
        # uses the parent's legal name and sometimes the operating name.
        for raw in (row["company_name_fda"], row["company_name_compustat"]):
            key = normalize_name(raw)
            if not key:
                continue
            if key in exact and exact[key]["gvkey"] != meta["gvkey"]:
                ambiguous.add(key)      # same name, two firms - refuse to guess
                continue
            exact[key] = meta

    for key in ambiguous:
        exact.pop(key, None)
    if ambiguous:
        print(f"    dropped {len(ambiguous)} ambiguous names (map to >1 gvkey)")

    MIN_PREFIX_LEN = 6
    prefix_keys = sorted([k for k in exact if len(k) >= MIN_PREFIX_LEN],
                         key=len, reverse=True)

    print(f"    sample firms (gvkey) : {cx['gvkey'].nunique():,}")
    print(f"    Tier A exact keys    : {len(exact):,}")
    print(f"    Tier B prefix keys   : {len(prefix_keys):,} "
          f"(>= {MIN_PREFIX_LEN} chars)")
    return exact, prefix_keys


def resolve_manufacturer(norm_key: str, exact: dict, prefix_keys: list,
                         memo: dict) -> tuple:
    """
    Map a normalized manufacturer name to (meta, tier), memoized.

    MAUDE repeats the same few thousand manufacturer strings across 25M
    records, so memoizing turns the prefix scan from the dominant cost into a
    rounding error.
    """
    if norm_key in memo:
        return memo[norm_key]

    result = (None, None)
    if norm_key in exact:
        result = (exact[norm_key], "A_exact")
    else:
        # Longest prefix wins, so 'MEDTRONIC MINIMED' beats 'MEDTRONIC' when
        # both are sample firms in their own right.
        for key in prefix_keys:
            if norm_key.startswith(key + " "):
                result = (exact[key], "B_prefix")
                break
    memo[norm_key] = result
    return result


# =============================================================
# STEP 3. Stream one partition and keep matching records
# =============================================================
def flatten_record(rec: dict, keep_text: bool) -> dict:
    """
    Flatten one MDR into a single row: top-level scalars plus the first device
    entry. Patient and narrative blocks are summarized, not expanded, so the
    output stays one row per report.
    """
    out = {f: rec.get(f) for f in EVENT_FIELDS}

    devices = rec.get("device") or []
    d0 = devices[0] if devices else {}
    out["n_devices_listed"] = len(devices)
    out["manufacturer_d_name"] = d0.get("manufacturer_d_name")
    out["brand_name"] = d0.get("brand_name")
    out["generic_name"] = d0.get("generic_name")
    out["model_number"] = d0.get("model_number")
    out["device_report_product_code"] = d0.get("device_report_product_code")
    out["device_class"] = (d0.get("openfda") or {}).get("device_class")
    out["medical_specialty"] = (d0.get("openfda") or {}).get(
        "medical_specialty_description")
    out["implant_flag"] = d0.get("implant_flag")
    out["device_operator"] = d0.get("device_operator")

    patients = rec.get("patient") or []
    out["n_patients_listed"] = len(patients)

    # Product problem codes describe WHAT went wrong with the device - the
    # closest thing MAUDE has to a severity/type taxonomy.
    # NOTE: the array can contain nulls (openFDA emits [null] for some older
    # reports), so entries are filtered and coerced before joining. A bare
    # "; ".join(probs) raises TypeError and killed 163 of 362 partitions on
    # the first full run.
    probs = rec.get("product_problems") or []
    probs = [str(p) for p in probs if p is not None]
    out["product_problems"] = "; ".join(probs) if probs else None

    if keep_text:
        texts = rec.get("mdr_text") or []
        out["mdr_text"] = " || ".join(
            str(t.get("text")) for t in texts
            if isinstance(t, dict) and t.get("text"))

    return out


def stream_partition(url: str, exact: dict, prefix_keys: list, memo: dict,
                     keep_text: bool, unmatched: Counter) -> pd.DataFrame:
    """
    Download one partition, keep only sample-firm records, return them.

    The partition bytes are never written to disk - they live in memory only
    long enough to filter, then are released. This is what keeps a pull over an
    18 GB archive fit in ~100 MB of working space.
    """
    resp = requests.get(url, timeout=1800)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            payload = json.load(fh)
    records = payload.get("results", [])
    del resp, payload

    kept = []
    for rec in records:
        devices = rec.get("device") or []
        meta = tier = None
        # Scan every listed device: the sample firm is not always device #1.
        for d in devices:
            name = d.get("manufacturer_d_name")
            if not name:
                continue
            meta, tier = resolve_manufacturer(normalize_name(name), exact,
                                              prefix_keys, memo)
            if meta is not None:
                break
        if meta is None:
            # Track the biggest misses so the worklist shows where the
            # remaining sample is hiding.
            nm = (devices[0].get("manufacturer_d_name") if devices else None)
            if nm:
                unmatched[normalize_name(nm)] += 1
            continue

        row = flatten_record(rec, keep_text)
        row["gvkey"] = meta["gvkey"]
        row["company_name_compustat"] = meta["company_name_compustat"]
        row["link_tier"] = tier
        row["match_source_crosswalk"] = meta["match_source_crosswalk"]
        row["review_suggested"] = meta["review_suggested"]
        row["_valid_from"] = meta["valid_from_year"]
        row["_valid_to"] = meta["valid_to_year"]
        kept.append(row)

    del records
    gc.collect()
    return pd.DataFrame(kept)


def enforce_ownership_window(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop reports that fall outside the ownership window of the matched firm.

    Same rule as scripts 05 and 10: an MDR belongs to whoever owned the
    manufacturer WHEN THE EVENT WAS REPORTED. Without this, every adverse
    event in Covidien's history would be attributed to Medtronic from 1991,
    which would badly distort any event-time analysis around acquisitions.
    """
    if df.empty:
        return df
    yr = pd.to_datetime(df["date_received"], format="%Y%m%d",
                        errors="coerce").dt.year
    # Fall back to date_of_event where the received date is unparseable.
    alt = pd.to_datetime(df["date_of_event"], format="%Y%m%d",
                         errors="coerce").dt.year
    yr = yr.fillna(alt)
    keep = yr.isna() | ((yr >= df["_valid_from"]) & (yr <= df["_valid_to"]))
    return df[keep].copy()


# =============================================================
# STEP 4. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    keep_text = "--keep-text" in sys.argv
    resume = "--resume" in sys.argv
    since = None
    if "--since" in sys.argv:
        since = int(sys.argv[sys.argv.index("--since") + 1])

    out_path = PROCESSED_DIR / f"part803_adverse_events_{snapshot_date}.csv.gz"
    manifest_path = PROCESSED_DIR / f"part803_manifest_{snapshot_date}.json"
    work_path = PROCESSED_DIR / f"part803_unmatched_manufacturers_{snapshot_date}.csv"

    print("=" * 64)
    print("FDA Part 803 - Medical Device Reports (MAUDE adverse events)")
    print(f"Snapshot date: {snapshot_date}")
    if since:
        print(f"Restricted to partitions from {since} onward")
    print("=" * 64)

    # --- 4a. Sample-firm name index. ---
    print("[1/4] Building sample-firm name index ...")
    exact, prefix_keys = build_name_index()

    # --- 4b. Partition list. ---
    print("[2/4] Reading openFDA download manifest ...")
    node = requests.get(DOWNLOAD_MANIFEST, timeout=120).json()["results"]["device"]["event"]
    partitions = node["partitions"]
    if node["total_records"] < MIN_EXPECTED_TOTAL:
        raise RuntimeError(
            f"Manifest reports only {node['total_records']:,} records "
            f"(expected >= {MIN_EXPECTED_TOTAL:,}). Aborting.")
    print(f"    export_date={node['export_date']}, "
          f"{node['total_records']:,} reports, {len(partitions)} partitions")

    def partition_year(p):
        """Extract the year from a partition URL like '.../2023q1/...'."""
        m = re.search(r"/(\d{4})q\d/", p["file"])
        return int(m.group(1)) if m else None

    def partition_tag(p):
        """
        Unique cache tag for one partition, e.g. '2026q1__0001-of-0009'.

        MUST include the file number, not just the quarter. A quarter can hold
        many partitions (2026q1 has 9), so tagging by quarter alone makes every
        partition in a quarter write to the same chunk file - each overwriting
        the last, silently discarding all but the final one. That bug cost 93%
        of the records on the first smoke test; the file-number suffix is what
        prevents it. It also makes --resume correct, since resume skips on the
        existence of a chunk file.
        """
        quarter = re.search(r"/(\d{4}q\d)/", p["file"])
        quarter = quarter.group(1) if quarter else "unknown"
        stem = p["file"].rsplit("/", 1)[-1]
        stem = stem.replace("device-event-", "").replace(".json.zip", "")
        return f"{quarter}__{stem}"

    if since:
        partitions = [p for p in partitions
                      if (partition_year(p) or 0) >= since]
        print(f"    {len(partitions)} partitions after --since filter")

    # --- 4c. Stream. ---
    print(f"[3/4] Streaming {len(partitions)} partitions "
          f"(this is the long part) ...")
    memo, unmatched = {}, Counter()
    total_kept, total_scanned = 0, 0
    started = time.time()

    for i, part in enumerate(partitions, start=1):
        tag = partition_tag(part)
        chunk_path = CACHE_DIR / f"{tag}.parquet"

        # --resume: a partition already written is trusted and skipped. Chunks
        # are per-partition, so an interrupted run loses at most one partition.
        if resume and chunk_path.exists():
            print(f"    [{i}/{len(partitions)}] {tag}: cached, skipping")
            continue

        try:
            df = stream_partition(part["file"], exact, prefix_keys, memo,
                                  keep_text, unmatched)
        except Exception as exc:  # noqa: BLE001 - one bad partition must not kill a 4-hour run
            print(f"    [{i}/{len(partitions)}] {tag}: FAILED ({exc}) - "
                  f"re-run with --resume to retry")
            continue

        df = enforce_ownership_window(df)
        df.to_parquet(chunk_path, index=False)
        total_kept += len(df)
        elapsed = time.time() - started
        rate = i / max(elapsed / 60, 0.01)
        eta = (len(partitions) - i) / max(rate, 0.01)
        print(f"    [{i}/{len(partitions)}] {tag}: kept {len(df):,} "
              f"(cum {total_kept:,}) | {rate:.1f} part/min | ETA {eta:.0f} min")
        del df
        gc.collect()

    # --- 4d. Concatenate, write, summarize. ---
    print("[4/4] Concatenating chunks and writing output ...")
    # Only concatenate chunks belonging to THIS run's partition list. Globbing
    # the whole cache would silently fold in chunks left by an earlier, wider
    # run (e.g. a --since 2005 run followed by --since 2020), producing an
    # output file that does not match the arguments it was called with.
    wanted_tags = {partition_tag(p) for p in partitions}
    chunks = sorted(c for c in CACHE_DIR.glob("*.parquet")
                    if c.stem in wanted_tags)
    print(f"    {len(chunks)} chunks in scope of {len(partitions)} partitions "
          f"({len(list(CACHE_DIR.glob('*.parquet')))} cached in total)")

    # A chunk count below the partition count means partitions failed and were
    # skipped by the error handler. Say so loudly - a silently short run is the
    # failure mode most likely to corrupt downstream counts.
    if len(chunks) < len(partitions):
        print(f"    WARNING: {len(partitions) - len(chunks)} partition(s) "
              f"missing - re-run with --resume to fill the gaps")

    frames = [pd.read_parquet(c) for c in chunks]
    if not frames:
        raise RuntimeError("No partitions were successfully processed.")
    out = pd.concat(frames, ignore_index=True)
    out = out.drop(columns=["_valid_from", "_valid_to"], errors="ignore")

    # Parse the two dates that drive event time into ISO form.
    for col in ["date_of_event", "date_received", "date_report_to_fda"]:
        out[col] = pd.to_datetime(out[col], format="%Y%m%d", errors="coerce")

    out.to_csv(out_path, index=False, compression="gzip", encoding="utf-8-sig")
    print(f"    processed -> {out_path.relative_to(REPO_ROOT)}")

    work = (pd.DataFrame(unmatched.most_common(3000),
                         columns=["normalized_manufacturer", "n_reports"]))
    work.to_csv(work_path, index=False, encoding="utf-8-sig")
    print(f"    worklist  -> {work_path.relative_to(REPO_ROOT)}")

    manifest = {
        "snapshot_date": snapshot_date,
        "openfda_export_date": node["export_date"],
        "openfda_total_records": node["total_records"],
        "partitions_processed": len(chunks),
        "partitions_available": len(node["partitions"]),
        "since_filter": since,
        "keep_text": keep_text,
        "records_kept": int(len(out)),
        "distinct_gvkeys": int(out["gvkey"].nunique()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"    manifest  -> {manifest_path.relative_to(REPO_ROOT)}")

    print("\nSummary")
    print(f"  MDRs kept              : {len(out):,}")
    print(f"  distinct firms (gvkey) : {out['gvkey'].nunique():,}")
    print(f"  Tier A (exact)         : {int((out['link_tier'] == 'A_exact').sum()):,}")
    print(f"  Tier B (prefix, review): {int((out['link_tier'] == 'B_prefix').sum()):,}")
    dates = out["date_received"].dropna()
    if len(dates):
        print(f"  date_received range    : {dates.min().date()} to {dates.max().date()}")
    print("  top firms by MDR count:")
    for name, n in out.groupby("company_name_compustat").size().nlargest(10).items():
        print(f"     {str(name)[:38]:<40} {n:,}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
