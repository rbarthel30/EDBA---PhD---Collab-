# =============================================================
# Script: 14_build_gvkey_year_event_panel.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Build THE analysis panel - one comprehensive gvkey-year-event table
#          unifying all three stages of the medical-device regulatory timeline:
#
#              adverse_event  (Part 803, MAUDE)      - script 11
#              recall         (Part 806, corrections/removals) - script 10
#              warning_letter (FDA compliance actions)         - script 03
#
#          This REPLACES the three standalone linked datasets. Every row is
#          tagged with `event_type`, so any single stage can be recovered with
#          one filter and the three can be compared on identical firm-year
#          scaffolding.
#
# GRAIN:   one row per (gvkey, year, event_type), carrying the event COUNT plus
#          stage-specific detail. Chosen over one-row-per-event because the
#          disclosure outcomes this feeds are measured at the firm-year level
#          (10-K/8-K/earnings-call), so a firm-year grain is what the analysis
#          actually consumes. Event-level detail stays reachable in the raw
#          snapshots under data/raw/.
#
# ---------------------------------------------------------------------------
# SAMPLE RULE - "matched to Compustat AS OF THE EVENT YEAR"
#
#   An event enters the panel only if its firm resolves to a gvkey whose
#   OWNERSHIP WINDOW contains the event year:
#         valid_from_year <= event_year <= valid_to_year
#   This is what stops a plant's pre-acquisition history being attributed to
#   the acquirer - a real risk in medtech, where Covidien, Guidant, St Jude
#   and Biomet all changed hands inside the sample window.
#
#   ⚠️ LIMITATION - THIS IS NOT A TEST OF COMPUSTAT COVERAGE IN THAT YEAR.
#   It verifies the firm was OWNED by that gvkey in the event year. It does
#   NOT verify the firm had an actual Compustat record (non-missing financials)
#   in that year, because that requires comp.funda from WRDS, which is not
#   cached locally and could not be pulled non-interactively (2026-07-19).
#   Table 1 (script 09) applies the stronger test for the letter sample.
#   To add it here: pull comp.funda, then gate on a non-missing observation at
#   the firm's fiscal year-end in `year`. Placeholder hook: apply_funda_gate().
# ---------------------------------------------------------------------------
#
# Inputs:  data/processed/fda_compliance_actions_<DATE>.csv            (script 03)
#          data/processed/part806_corrections_removals_<DATE>.csv      (script 10)
#          data/processed/part803_adverse_events_<DATE>.csv.gz         (script 11)
#          data/processed/fda_firm_gvkey_crosswalk_unified_<DATE>.csv  (script 12)
#          data/raw/compustat_company_<DATE>.csv                       (firm metadata)
# Outputs: data/processed/gvkey_year_event_panel_<DATE>.csv            (THE panel)
#          output/tables/panel_descriptives_<DATE>.md                  (descriptives)
#
# Usage:   python scripts/14_build_gvkey_year_event_panel.py
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

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
TABLES_DIR = REPO_ROOT / "output" / "tables"

WRDS_USERNAME = os.environ.get("WRDS_USERNAME", "rxb1406")

# MAUDE is ~10.7M rows; read it in chunks so peak memory stays modest.
MAUDE_CHUNK = 1_000_000

EVENT_TYPES = ["warning_letter", "recall", "adverse_event"]


# =============================================================
# STEP 1. Shared helpers
# =============================================================
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


def latest(directory: Path, pattern: str, required: bool = True):
    """Return the most recent date-stamped file matching a glob pattern."""
    hits = sorted(glob.glob(str(directory / pattern)))
    if not hits:
        if required:
            raise FileNotFoundError(f"No file matches {pattern} in {directory}")
        return None
    return Path(hits[-1])


def load_ownership_windows() -> pd.DataFrame:
    """
    Load the unified crosswalk reduced to what the sample rule needs:
    normalized name -> gvkey plus the ownership window.

    Where a name appears more than once the WIDEST window is kept, so the gate
    never rejects an event that any crosswalk row would have admitted; the
    narrower provenance stays in the crosswalk file itself.
    """
    cx = pd.read_csv(latest(PROCESSED_DIR,
                            "fda_firm_gvkey_crosswalk_unified_*.csv"),
                     low_memory=False)
    cx = cx[cx["gvkey"].notna()].copy()
    cx["gvkey"] = cx["gvkey"].astype("int64")
    cx["valid_from_year"] = cx["valid_from_year"].fillna(1900).astype(int)
    cx["valid_to_year"] = cx["valid_to_year"].fillna(2099).astype(int)
    win = (cx.groupby(["normalized_name", "gvkey"])
             .agg(valid_from_year=("valid_from_year", "min"),
                  valid_to_year=("valid_to_year", "max"))
             .reset_index())

    # Report how much of this window data is REAL. Almost all rows default to
    # 1900-2099, which means the gate below is near-vacuous - a fact that must
    # be visible at run time, not buried in a doc. See the header limitation.
    trivial = ((win["valid_from_year"] <= 1900)
               & (win["valid_to_year"] >= 2099))
    print(f"    ownership windows: {len(win):,} name-gvkey pairs, "
          f"{win['gvkey'].nunique():,} firms")
    print(f"    WARNING - REAL windows: {int((~trivial).sum()):,} of {len(win):,} "
          f"({(~trivial).mean():.1%}) - the rest default to 1900-2099, so the "
          f"ownership gate is effectively NON-BINDING")
    return win


def apply_window_gate(df: pd.DataFrame, year_col: str) -> pd.DataFrame:
    """
    Enforce the sample rule: keep an event only if its year falls inside the
    matched firm's ownership window. Rejections are counted, not silently
    dropped, so the cost of the rule is visible in the log.
    """
    before = len(df)
    keep = ((df[year_col] >= df["valid_from_year"])
            & (df[year_col] <= df["valid_to_year"]))
    out = df[keep].copy()
    print(f"       ownership-window gate: kept {len(out):,} of {before:,} "
          f"({len(out) / max(before, 1):.1%})")
    return out


def fetch_funda(gvkeys, refresh: bool) -> pd.DataFrame:
    """
    Pull comp.funda for the panel's firms and cache the raw extract.

    Standard Compustat filters are applied in SQL (indfmt/datafmt/popsrc/
    consol). Without them Compustat returns several rows per firm-year for
    alternative reporting formats, which would inflate any presence test.

    The licensed extract is written to data/raw/ (gitignored) so the gate can
    be re-applied later without a WRDS round-trip.
    """
    cached = latest(RAW_DIR, "compustat_funda_*.csv", required=False)
    if cached is not None and not refresh:
        print(f"    using cached funda extract: {cached.name}")
        return pd.read_csv(cached, low_memory=False)

    import wrds
    print("    connecting to WRDS ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        keys = ", ".join(f"'{int(g):06d}'" for g in sorted(set(gvkeys)))
        funda = db.raw_sql(
            "select gvkey, datadate, fyear, at, prcc_f, csho, sale, ni "
            "from comp.funda "
            "where indfmt='INDL' and datafmt='STD' and popsrc='D' "
            "and consol='C' "
            f"and gvkey in ({keys})")
    finally:
        db.close()

    out_path = RAW_DIR / f"compustat_funda_{date.today().isoformat()}.csv"
    funda.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    pulled {len(funda):,} firm-years -> "
          f"{out_path.relative_to(REPO_ROOT)}")
    return funda


def build_active_firm_years(funda: pd.DataFrame) -> tuple:
    """
    Build the set of (gvkey, year) cells where the firm was ACTIVE.

    'Active' = a Compustat annual record exists for that fiscal year AND
    market capitalization is computable (non-missing `prcc_f` and `csho`).
    That is deliberately the same test Table 1 (script 09) applies, so the
    panel and Table 1 rest on one definition rather than two.

    Requiring computable market cap - rather than merely 'a row exists' - is
    what makes this a test of being PUBLICLY TRADED at the time, which is the
    real precondition for observing a disclosure response at all.

    Returns (active_set, any_record_set) so the cost of the strict rule can be
    reported against the looser alternative.
    """
    f = funda.copy()
    f["gvkey"] = pd.to_numeric(f["gvkey"], errors="coerce").astype("Int64")
    # fyear is Compustat's fiscal-year label and is the right key for an
    # annual panel; fall back to the calendar year of datadate where fyear is
    # missing (rare, but present in older records).
    yr = pd.to_numeric(f["fyear"], errors="coerce")
    alt = pd.to_datetime(f["datadate"], errors="coerce").dt.year
    f["year"] = yr.fillna(alt)
    f = f[f["gvkey"].notna() & f["year"].notna()].copy()
    f["year"] = f["year"].astype(int)

    any_record = set(zip(f["gvkey"].astype(int), f["year"]))
    tradeable = f[f["prcc_f"].notna() & f["csho"].notna()]
    active = set(zip(tradeable["gvkey"].astype(int), tradeable["year"]))

    print(f"    funda firm-years            : {len(f):,}")
    print(f"    ... with ANY record         : {len(any_record):,} cells")
    print(f"    ... with computable mktcap  : {len(active):,} cells  "
          f"<- the gate")
    return active, any_record


def apply_funda_gate(panel: pd.DataFrame, active: set,
                     any_record: set) -> pd.DataFrame:
    """
    Drop panel rows whose (gvkey, year) was not an active, publicly traded
    Compustat firm-year.

    Both the strict and loose rejection counts are reported, because the gap
    between them is exactly the population of firms that exist in Compustat
    but were not trading - the ones whose disclosure response is unobservable.
    """
    cells = list(zip(panel["gvkey"], panel["year"]))
    in_active = pd.Series([c in active for c in cells], index=panel.index)
    in_any = pd.Series([c in any_record for c in cells], index=panel.index)

    before = len(panel)
    print(f"    panel rows before gate      : {before:,}")
    print(f"    ... firm-year in Compustat  : {int(in_any.sum()):,} "
          f"({in_any.mean():.1%})")
    print(f"    ... AND publicly traded     : {int(in_active.sum()):,} "
          f"({in_active.mean():.1%})  <- kept")
    print(f"    dropped                     : {before - int(in_active.sum()):,}")
    return panel[in_active].copy()


# =============================================================
# STEP 2. Warning letters -> gvkey-year counts
# =============================================================
def build_warning_letters(win: pd.DataFrame) -> pd.DataFrame:
    """
    Device warning letters, counted by UNIQUE Case/Injunction ID.

    Counting rows would double-count: one letter can span several
    establishments or product types, which is the documented gotcha in
    data/README.md.
    """
    ca = pd.read_csv(latest(PROCESSED_DIR, "fda_compliance_actions_*.csv"),
                     low_memory=False)
    dev = ca[ca["is_device"] & ca["is_warning_letter"]].copy()
    dev = dev.drop_duplicates("Case/Injunction ID")
    dev["year"] = pd.to_datetime(dev["action_taken_date"],
                                 errors="coerce").dt.year
    dev["normalized_name"] = dev["company_name_clean"].map(normalize_name)
    dev = dev[dev["year"].notna()]
    dev["year"] = dev["year"].astype(int)

    merged = dev.merge(win, on="normalized_name", how="inner")
    merged = apply_window_gate(merged, "year")

    out = (merged.groupby(["gvkey", "year"])
           .agg(n_events=("Case/Injunction ID", "nunique"))
           .reset_index())
    out["event_type"] = "warning_letter"
    print(f"       -> {len(out):,} gvkey-year rows, "
          f"{out['n_events'].sum():,} letters")
    return out


# =============================================================
# STEP 3. Recalls -> gvkey-year counts
# =============================================================
def build_recalls(win: pd.DataFrame) -> pd.DataFrame:
    """
    Part 806 corrections and removals, counted by unique recall record, with
    severity split out.

    Event time is the date the FIRM INITIATED the action - that is the
    managerial decision the paper is about - falling back to FDA's posting
    date only where initiation is missing.
    """
    rc = pd.read_csv(latest(PROCESSED_DIR, "part806_corrections_removals_*.csv"),
                     low_memory=False)
    init = pd.to_datetime(rc["event_date_initiated"], errors="coerce")
    post = pd.to_datetime(rc["event_date_posted"], errors="coerce")
    rc["year"] = init.fillna(post).dt.year
    rc = rc[rc["year"].notna() & rc["gvkey"].notna()].copy()
    rc["year"] = rc["year"].astype(int)
    rc["gvkey"] = rc["gvkey"].astype("int64")

    # Re-apply the window gate on the UNIFIED crosswalk, joining PER NAME
    # rather than per gvkey. Collapsing windows to min/max within a gvkey
    # would widen any real window back out to 1900-2099 as soon as one
    # Compustat-direct row (which has no window) shares that gvkey - silently
    # nullifying the sample rule this function exists to enforce.
    rc["normalized_name"] = rc["recalling_firm"].map(normalize_name)
    rc = rc.merge(win, on=["normalized_name", "gvkey"], how="left")
    # Names with no crosswalk row for this gvkey keep the permissive default:
    # they were linked by FEI, not by name, so no window is knowable.
    rc["valid_from_year"] = rc["valid_from_year"].fillna(1900).astype(int)
    rc["valid_to_year"] = rc["valid_to_year"].fillna(2099).astype(int)
    rc = apply_window_gate(rc, "year")

    cls = rc["classification"].fillna("")
    rc["is_class_i"] = cls.eq("Class I")
    rc["is_class_ii"] = cls.eq("Class II")
    rc["is_class_iii"] = cls.eq("Class III")

    out = (rc.groupby(["gvkey", "year"])
           .agg(n_events=("cfres_id", "nunique"),
                n_recall_class_i=("is_class_i", "sum"),
                n_recall_class_ii=("is_class_ii", "sum"),
                n_recall_class_iii=("is_class_iii", "sum"))
           .reset_index())
    out["event_type"] = "recall"
    print(f"       -> {len(out):,} gvkey-year rows, "
          f"{out['n_events'].sum():,} recalls")
    return out


# =============================================================
# STEP 4. MAUDE adverse events -> gvkey-year counts
# =============================================================
def build_adverse_events(win: pd.DataFrame) -> pd.DataFrame:
    """
    Part 803 adverse-event reports aggregated to gvkey-year, read in chunks.

    Tier A (exact name match) and Tier B (parent-prefix, review-flagged) are
    counted SEPARATELY as well as together. Tier B is ~44% of all matched
    reports and skews toward large acquisitive firms, so any result that moves
    when Tier B is excluded needs to be reported both ways - keeping the split
    in the panel makes that a one-line robustness check rather than a re-run.
    """
    path = latest(PROCESSED_DIR, "part803_adverse_events_*.csv.gz")

    parts, n_raw, n_gated = [], 0, 0
    reader = pd.read_csv(path, low_memory=False, chunksize=MAUDE_CHUNK,
                         usecols=["gvkey", "date_received", "date_of_event",
                                  "link_tier", "manufacturer_d_name"])
    for i, chunk in enumerate(reader, start=1):
        n_raw += len(chunk)
        rec = pd.to_datetime(chunk["date_received"], errors="coerce")
        evt = pd.to_datetime(chunk["date_of_event"], errors="coerce")
        # date_received is the regulatory clock (when FDA got the report) and
        # is far better populated than date_of_event, so it leads.
        chunk["year"] = rec.fillna(evt).dt.year
        chunk = chunk[chunk["year"].notna() & chunk["gvkey"].notna()].copy()
        chunk["year"] = chunk["year"].astype(int)
        chunk["gvkey"] = chunk["gvkey"].astype("int64")

        # Per-name window join, for the same reason as the recall path.
        chunk["normalized_name"] = chunk["manufacturer_d_name"].map(normalize_name)
        chunk = chunk.merge(win, on=["normalized_name", "gvkey"], how="left")
        chunk["valid_from_year"] = chunk["valid_from_year"].fillna(1900).astype(int)
        chunk["valid_to_year"] = chunk["valid_to_year"].fillna(2099).astype(int)
        keep = ((chunk["year"] >= chunk["valid_from_year"])
                & (chunk["year"] <= chunk["valid_to_year"]))
        chunk = chunk[keep]
        n_gated += len(chunk)

        chunk["is_tier_a"] = chunk["link_tier"].eq("A_exact")
        chunk["is_tier_b"] = chunk["link_tier"].eq("B_prefix")
        parts.append(chunk.groupby(["gvkey", "year"])
                     .agg(n_events=("link_tier", "size"),
                          n_mdr_tier_a=("is_tier_a", "sum"),
                          n_mdr_tier_b=("is_tier_b", "sum"))
                     .reset_index())
        print(f"       chunk {i}: {n_raw:,} read, {n_gated:,} kept")

    out = (pd.concat(parts, ignore_index=True)
           .groupby(["gvkey", "year"]).sum().reset_index())
    out["event_type"] = "adverse_event"
    print(f"       ownership-window gate: kept {n_gated:,} of {n_raw:,} "
          f"({n_gated / max(n_raw, 1):.1%})")
    print(f"       -> {len(out):,} gvkey-year rows, "
          f"{out['n_events'].sum():,} reports")
    return out


# =============================================================
# STEP 5. Assemble, attach firm metadata, describe
# =============================================================
def attach_firm_metadata(panel: pd.DataFrame) -> pd.DataFrame:
    """Attach Compustat name, SIC and status so the panel is self-describing."""
    comp = pd.read_csv(latest(RAW_DIR, "compustat_company_*.csv"),
                       low_memory=False)
    comp = comp[["gvkey", "conm", "sic", "costat", "cik"]].copy()
    comp["gvkey"] = comp["gvkey"].astype("int64")
    comp = comp.rename(columns={"conm": "company_name_compustat"})
    comp = comp.drop_duplicates("gvkey")
    return panel.merge(comp, on="gvkey", how="left")


def describe(panel: pd.DataFrame, snapshot_date: str) -> str:
    """
    Build the descriptive block reported to the console AND written to
    output/tables/, so the numbers quoted in the paper have a dated artefact
    behind them rather than living only in a terminal scrollback.
    """
    lines = []
    add = lines.append
    add(f"# Panel descriptives - gvkey-year-event ({snapshot_date})\n")

    add("## Overall\n")
    add("| Statistic | Value |")
    add("|:---|---:|")
    add(f"| Total gvkey-year-event observations | {len(panel):,} |")
    add(f"| Unique firms (gvkey) | {panel['gvkey'].nunique():,} |")
    add(f"| Unique gvkey-year cells | "
        f"{panel.groupby(['gvkey', 'year']).ngroups:,} |")
    add(f"| Year range | {panel['year'].min()}-{panel['year'].max()} |")
    add(f"| Total underlying events | {int(panel['n_events'].sum()):,} |\n")

    add("## By event type\n")
    add("| Event type | Obs (gvkey-year) | Firms | Events | Median/cell |")
    add("|:---|---:|---:|---:|---:|")
    for et in EVENT_TYPES:
        s = panel[panel["event_type"] == et]
        if s.empty:
            continue
        add(f"| {et} | {len(s):,} | {s['gvkey'].nunique():,} | "
            f"{int(s['n_events'].sum()):,} | {s['n_events'].median():.0f} |")
    add("")

    # How often do the three stages co-occur? This is the number that tells us
    # whether a within-firm-year timeline analysis is even feasible.
    wide = (panel.pivot_table(index=["gvkey", "year"], columns="event_type",
                              values="n_events", aggfunc="sum")
            .fillna(0))
    for et in EVENT_TYPES:
        if et not in wide:
            wide[et] = 0
    n_cells = len(wide)
    add("## Co-occurrence within a gvkey-year\n")
    add("| Combination | gvkey-years | Share |")
    add("|:---|---:|---:|")
    combos = [
        ("warning letter only", (wide.warning_letter > 0) & (wide.recall == 0)
         & (wide.adverse_event == 0)),
        ("recall only", (wide.recall > 0) & (wide.warning_letter == 0)
         & (wide.adverse_event == 0)),
        ("adverse event only", (wide.adverse_event > 0)
         & (wide.warning_letter == 0) & (wide.recall == 0)),
        ("letter + recall", (wide.warning_letter > 0) & (wide.recall > 0)),
        ("letter + adverse event", (wide.warning_letter > 0)
         & (wide.adverse_event > 0)),
        ("recall + adverse event", (wide.recall > 0) & (wide.adverse_event > 0)),
        ("ALL THREE", (wide.warning_letter > 0) & (wide.recall > 0)
         & (wide.adverse_event > 0)),
    ]
    for label, mask in combos:
        add(f"| {label} | {int(mask.sum()):,} | {mask.sum() / n_cells:.1%} |")
    add("")

    add("## Firms by event-type coverage\n")
    fw = (panel.pivot_table(index="gvkey", columns="event_type",
                            values="n_events", aggfunc="sum").fillna(0))
    for et in EVENT_TYPES:
        if et not in fw:
            fw[et] = 0
    add("| Firm appears in | Firms |")
    add("|:---|---:|")
    add(f"| Warning letters | {int((fw.warning_letter > 0).sum()):,} |")
    add(f"| Recalls | {int((fw.recall > 0).sum()):,} |")
    add(f"| Adverse events | {int((fw.adverse_event > 0).sum()):,} |")
    add(f"| **All three sources** | "
        f"{int(((fw > 0).sum(axis=1) == 3).sum()):,} |")
    add("")

    add("*Sample rule:* an event enters the panel only if its firm resolves "
        "to a Compustat gvkey whose ownership window contains the event year.")
    add("")
    add("**Compustat active-firm-year gate (binding).** An event is kept "
        "only if its firm has a `comp.funda` annual record for that fiscal "
        "year AND market capitalisation is computable (non-missing `prcc_f` "
        "and `csho`) - i.e. the firm was publicly traded that year, the "
        "precondition for observing any disclosure response. This is the "
        "same test Table 1 (script 09) applies, so the panel and Table 1 now "
        "share one definition.")
    add("")
    add("> *Note:* the crosswalk ownership-window gate is retained but is "
        "near-vacuous on its own - only 2 of 630 name-gvkey pairs carry a "
        "real window, the rest defaulting to 1900-2099. The funda gate above "
        "is what actually binds.")
    add("")
    add("*Other notes:* warning letters are counted by unique FDA "
        "Case/Injunction ID. MAUDE counts include Tier B parent-prefix "
        "matches (~44% of reports), split out in `n_mdr_tier_a` / "
        "`n_mdr_tier_b`.")
    return "\n".join(lines)


# =============================================================
# STEP 6. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("gvkey-year-event panel - FDA medical-device regulatory timeline")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 64)

    print("[1/6] Loading ownership windows from the unified crosswalk ...")
    win = load_ownership_windows()

    print("[2/6] Warning letters ...")
    wl = build_warning_letters(win)
    print("[3/6] Recalls (Part 806) ...")
    rc = build_recalls(win)
    print("[4/6] Adverse events (Part 803 MAUDE) ...")
    ae = build_adverse_events(win)

    print("[5/6] Assembling panel ...")
    panel = pd.concat([wl, rc, ae], ignore_index=True)
    print(f"    pre-gate: {len(panel):,} gvkey-year-event rows, "
          f"{panel['gvkey'].nunique():,} firms")

    print("[6/6] Applying the Compustat active-firm-year gate ...")
    funda = fetch_funda(panel["gvkey"].unique(), "--refresh-funda" in sys.argv)
    active, any_record = build_active_firm_years(funda)
    panel = apply_funda_gate(panel, active, any_record)
    panel = attach_firm_metadata(panel)

    # Stable, readable column order: keys first, then counts, then metadata.
    lead = ["gvkey", "year", "event_type", "n_events"]
    rest = [c for c in panel.columns if c not in lead]
    panel = panel[lead + rest].sort_values(["gvkey", "year", "event_type"])

    out_path = PROCESSED_DIR / f"gvkey_year_event_panel_{snapshot_date}.csv"
    panel.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    panel -> {out_path.relative_to(REPO_ROOT)}")

    md = describe(panel, snapshot_date)
    md_path = TABLES_DIR / f"panel_descriptives_{snapshot_date}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"    descriptives -> {md_path.relative_to(REPO_ROOT)}\n")
    print(md)
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
