# =============================================================
# Script: 18_build_combined_filing_event_dataset.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Build ONE combined dataset whose BASELINE is the full medical-device
#          10-K/10-Q panel (script 17 - every filing, whether or not anything
#          happened), with FDA product events and event 8-Ks merged in at the
#          gvkey x year x reporting-quarter level. Keeping every filing is the
#          point: disclosure in quarters WITH a product event can be compared
#          against disclosure in quarters WITHOUT one.
#
# GRAIN:   one row per 10-K/10-Q filing = one firm reporting quarter
#          (gvkey x reporting_year x reporting_quarter; a 10-K stands for the
#          fiscal 4th quarter). Event and 8-K columns are COUNTS for that
#          reporting quarter and are 0 when nothing happened.
#
# ---------------------------------------------------------------------------
# HOW AN EVENT GETS ITS REPORTING QUARTER
#
#   Each filing covers a reporting period ending on its period-of-report date.
#   An event dated d is assigned to the filing whose period CONTAINS d:
#
#         period_start  <  d  <=  period_end
#
#   where period_start is the previous filing's period end (or period_end
#   minus 3 months when there is no previous filing within ~a quarter, e.g. a
#   missing 10-Q). The event then inherits that filing's reporting_year /
#   reporting_quarter, and the merge key is gvkey-year-quarter.
#
#   WHY NOT just the calendar quarter of the event date: reporting quarters are
#   firm-specific. Medtronic's quarters end in Jan/Apr/Jul/Oct, and 52/53-week
#   filers end a few days off a month end (J&J: 2006-10-01). A calendar-quarter
#   key puts a mid-February Medtronic event in a period that ended in January -
#   BEFORE the event - and gives 150 filings a non-unique key. The window rule
#   also guarantees ORDERING: the filing for a period is filed after the period
#   ends, so every merged event precedes the filing it is attached to.
#
#   Event dates (same choices as script 14): warning letter = action-taken
#   date; recall = date the firm initiated it (FDA posting date if missing);
#   adverse event = date FDA received the report (event date if missing).
#   8-K = the 8-K's own reported event date (`period_ending`; filing date if
#   missing).
#
# EVENT SAMPLE: all events passing script 14's ownership-window gate. The
#   comp.funda "publicly traded" gate is NOT applied here - it would recode
#   event quarters of SEC filers without Compustat market cap (e.g. Biomet
#   post-LBO) as no-event quarters. It is carried as a flag instead
#   (`compustat_active_year`). The event loaders are reconciled against the
#   committed script-14 panel on every run (exact match required).
#
# Inputs:  data/processed/10k_10q_devices_2026-07-20.csv            (script 17)
#          data/processed/gvkey_year_event_panel_2026-07-19.csv     (script 14, reconciliation)
#          data/processed/fda_compliance_actions_2026-07-06.csv     (script 03)
#          data/processed/part806_corrections_removals_2026-07-19.csv (script 10 --use-cached)
#          %LOCALAPPDATA%/edba_fda_cache/part803_stream/*.parquet   (script 11 cache,
#                                           openFDA export 2026-07-14, 362 chunks)
#          data/processed/fda_firm_gvkey_crosswalk_unified_2026-07-19.csv (script 12)
#          data/processed/8k_device_event_disclosures_2026-07-19.csv (script 16)
#          data/raw/compustat_funda_2026-07-19.csv                  (flag only)
# Outputs: data/combined_9_17_26.csv
#          output/tables/descriptives_combined_9_17_26.md
#          meetings/descriptives_combined_9_17_26.pdf   (pdflatex / MiKTeX)
#
# Usage:   python scripts/18_build_combined_filing_event_dataset.py
# =============================================================

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# -------------------------------------------------------------
# STEP 0. Paths and constants
# -------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED = REPO_ROOT / "data" / "processed"
RAW = REPO_ROOT / "data" / "raw"

# Inputs are PINNED by name, not globbed: this is a dated deliverable tied to
# exact snapshots, and a glob once silently picked a `_SUPERSEDED` sibling.
FILINGS_PATH = PROCESSED / "10k_10q_devices_2026-07-20.csv"
PANEL_PATH = PROCESSED / "gvkey_year_event_panel_2026-07-19.csv"
LETTERS_PATH = PROCESSED / "fda_compliance_actions_2026-07-06.csv"
RECALLS_PATH = PROCESSED / "part806_corrections_removals_2026-07-19.csv"
EIGHTK_PATH = PROCESSED / "8k_device_event_disclosures_2026-07-19.csv"
FUNDA_PATH = RAW / "compustat_funda_2026-07-19.csv"
MAUDE_CACHE = Path(os.environ["LOCALAPPDATA"]) / "edba_fda_cache" / "part803_stream"
MAUDE_EXPECTED_CHUNKS = 362      # part803_manifest_2026-07-19.json

DATASET_NAME = "combined_9_17_26"
OUT_DATA = REPO_ROOT / "data" / f"{DATASET_NAME}.csv"
OUT_MD = REPO_ROOT / "output" / "tables" / f"descriptives_{DATASET_NAME}.md"
OUT_PDF = REPO_ROOT / "meetings" / f"descriptives_{DATASET_NAME}.pdf"
# Industry-coverage table (Step 7): current market cap of the panel firms as a
# share of the US medical-device universe - same definition as script 09's
# Table 1, recomputed for THIS panel. The WRDS pull is cached under data/raw/
# with a `compustat_` prefix, so it is gitignored (licensed; never committed).
# Only the aggregate statistics reach the committed descriptives.
UNIVERSE_CACHE = RAW / "compustat_device_universe_mktcap_2026-09-18.csv"
DEVICE_SICS = ("3841", "3842", "3843", "3844", "3845")
# "Current" market cap = prcc_f x csho at the firm's latest fiscal year-end on
# or after this date. Script 09 used 2024-06-30 in July 2026; moved forward one
# year so "current" means fiscal 2025 or later as of September 2026.
LIVE_CUTOFF = "2025-06-30"
WRDS_USERNAME = os.environ.get("WRDS_USERNAME", "rxb1406")

EVENT_TYPES = ["warning_letter", "recall", "adverse_event"]
EVENT_LABELS = {"warning_letter": "Warning letter",
                "recall": "Recall (Part 806)",
                "adverse_event": "Adverse event (Part 803)"}

# A period-of-report date this close to the filing date cannot be real; EDGAR
# has stamped the filing date into reportDate. Those period ends are imputed
# (Step 2). Threshold set from the data: 32 filings have a lag of 0-5 days
# (all reportDate == filing date, give or take a day), then nothing until
# genuine fast filers at 9+ days (Abiomed 9, Intuitive Surgical 17).
MIN_DAYS_PERIOD_TO_FILING = 8
# Two consecutive period ends further apart than this mean a filing is missing
# in between, so the later period's window must NOT stretch back to the earlier.
MAX_DAYS_BETWEEN_PERIODS = 120
# The FDA Data Dashboard compliance-actions file (script 03) begins in FY2009
# (first device letter in the sample: 2008-10-10). Before that, warning letters
# are UNOBSERVED, not absent - so a filing whose period starts earlier cannot be
# treated as a 'no warning letter' observation. Recalls (2000+) and MAUDE
# (1991+) both predate the first filing in the panel, so need no such flag.
WARNING_LETTER_DATA_START = pd.Timestamp("2008-10-01")


def load_script14():
    """Import script 14 as a module so its sample-rule helpers are REUSED
    (name normalization, ownership windows, funda 'active' test), not copied."""
    path = SCRIPT_DIR / "14_build_gvkey_year_event_panel.py"
    spec = importlib.util.spec_from_file_location("script14", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================
# STEP 1. Baseline: the full 10-K/10-Q panel
# =============================================================
def load_filings() -> pd.DataFrame:
    f = pd.read_csv(FILINGS_PATH, dtype={"cik": str})
    f["gvkey"] = f["gvkey"].astype("int64")
    assert f["accession"].is_unique, "accession not unique in the filing panel"
    assert set(f["form"]) <= {"10-K", "10-Q"}, set(f["form"])
    f["filing_date"] = pd.to_datetime(f["filing_date"])
    f["report_date"] = pd.to_datetime(f["report_date"])
    assert f["filing_date"].notna().all() and f["report_date"].notna().all()
    return f


# =============================================================
# STEP 2. Reporting periods: clean period end, window, year-quarter label
# =============================================================
def nearest_month_end(d: pd.Series) -> pd.Series:
    """Snap a date to the NEAREST month end (52/53-week filers end a few days
    either side of one: 2006-10-01 -> 2006-09-30, 2015-12-26 -> 2015-12-31)."""
    this_me = d + pd.offsets.MonthEnd(0)
    prev_me = d - pd.offsets.MonthEnd(1)
    return pd.Series(np.where(d.dt.day <= 15, prev_me, this_me), index=d.index)


def build_reporting_periods(f: pd.DataFrame) -> pd.DataFrame:
    f = f.sort_values(["gvkey", "filing_date"]).reset_index(drop=True)

    # --- 2a. Flag unusable period dates and impute them. ---
    lag = (f["filing_date"] - f["report_date"]).dt.days
    f["period_end_imputed"] = (lag < MIN_DAYS_PERIOD_TO_FILING).astype(int)
    f["period_end"] = f["report_date"].where(f["period_end_imputed"] == 0)

    # Firm's fiscal cycle = which months its quarters end in, as month % 3
    # (Mar/Jun/Sep/Dec -> 0, Jan/Apr/Jul/Oct -> 1, Feb/May/Aug/Nov -> 2), from
    # its reliable period ends.
    snapped = nearest_month_end(f["period_end"].dropna())
    cycle = (snapped.dt.month % 3).groupby(f.loc[snapped.index, "gvkey"]) \
        .agg(lambda s: s.mode().iloc[0])
    # Imputed period end = the latest on-cycle month end at least 20 days
    # before the filing date (a 10-Q is due 40-45 days after period end).
    for i in f.index[f["period_end_imputed"] == 1]:
        cyc = cycle.get(f.at[i, "gvkey"], 0)
        me = (f.at[i, "filing_date"] - pd.Timedelta(days=20)) + pd.offsets.MonthEnd(0)
        if me > f.at[i, "filing_date"] - pd.Timedelta(days=20):
            me = me - pd.offsets.MonthEnd(1)
        while me.month % 3 != cyc:
            me = me - pd.offsets.MonthEnd(1)
        f.at[i, "period_end"] = me
    f["period_end"] = pd.to_datetime(f["period_end"])

    # --- 2b. Reporting year-quarter LABEL (the merge key). ---
    # Calendar year and quarter of the period end snapped to its nearest month
    # end. For a non-calendar fiscal year this is a label for the period, not
    # the firm's own fiscal-quarter number (a 10-K marks the fiscal Q4).
    me = nearest_month_end(f["period_end"])
    f["reporting_year"] = me.dt.year.astype(int)
    f["reporting_quarter"] = me.dt.quarter.astype(int)

    # --- 2c. Period window (period_start, period_end]. ---
    f = f.sort_values(["gvkey", "period_end", "filing_date"]).reset_index(drop=True)
    prev_end = f.groupby("gvkey")["period_end"].shift(1)
    gap = (f["period_end"] - prev_end).dt.days
    default_start = f["period_end"] - pd.DateOffset(months=3)
    use_prev = prev_end.notna() & (gap > 0) & (gap <= MAX_DAYS_BETWEEN_PERIODS)
    f["period_start"] = prev_end.where(use_prev, default_start)

    # --- 2d. The key must be unique or the event merge would fan out. ---
    dup = f.duplicated(["gvkey", "reporting_year", "reporting_quarter"], keep=False)
    print(f"    period ends imputed (EDGAR reportDate ~ filing date): "
          f"{int(f['period_end_imputed'].sum())}")
    print(f"    windows anchored on previous filing: {int(use_prev.sum()):,} | "
          f"on period_end - 3 months: {int((~use_prev).sum()):,}")
    if dup.any():
        print(f[dup][["gvkey", "company", "form", "filing_date", "report_date",
                      "period_end"]].to_string())
        raise AssertionError("gvkey-reporting_year-reporting_quarter not unique")
    return f


def assign_to_period(events: pd.DataFrame, periods: pd.DataFrame,
                     date_col: str) -> pd.DataFrame:
    """
    Attach to each dated row the reporting period whose window contains it.
    Forward as-of match to the first period_end >= date within the firm, then
    require date > period_start. Rows with no containing period get NaN keys
    (firm not in the filing panel, before its first filing, or in a gap).
    """
    ev = events[events[date_col].notna()].sort_values(date_col)
    per = periods[["gvkey", "period_start", "period_end", "reporting_year",
                   "reporting_quarter"]].sort_values("period_end")
    out = pd.merge_asof(ev, per, left_on=date_col, right_on="period_end",
                        by="gvkey", direction="forward")
    inside = out["period_end"].notna() & (out[date_col] > out["period_start"])
    out.loc[~inside, ["period_start", "period_end", "reporting_year",
                      "reporting_quarter"]] = np.nan
    return out


def fiscal_year_windows(filings: pd.DataFrame) -> pd.DataFrame:
    """One row per 10-K with its fiscal-year window (fy_start, fy_end]: fy_start
    is the previous 10-K's period end, or period_end - 12 months when there is
    no previous 10-K within ~13 months (first 10-K in the panel, missing year)."""
    k = (filings[filings["form"] == "10-K"]
         .sort_values(["gvkey", "period_end"]).copy())
    prev_end = k.groupby("gvkey")["period_end"].shift(1)
    gap = (k["period_end"] - prev_end).dt.days
    use_prev = prev_end.notna() & (gap > 0) & (gap <= 400)
    k["fy_start"] = prev_end.where(use_prev, k["period_end"] - pd.DateOffset(years=1))
    k = k.rename(columns={"period_end": "fy_end", "accession": "fy_accession"})
    return k[["gvkey", "fy_start", "fy_end", "fy_accession"]]


def assign_to_fiscal_year(events: pd.DataFrame, filings: pd.DataFrame) -> pd.DataFrame:
    """
    Attach to each event the 10-K whose FISCAL YEAR contains it (returns the
    10-K's accession in `fy_accession`, NaN if none). Same window logic as the
    quarterly assignment, one level up: fy_start < date <= the 10-K's
    period_end, where fy_start is the previous 10-K's period end, or
    period_end - 12 months when there is no previous 10-K within ~13 months
    (first 10-K in the panel, or a missing year). Done directly on event dates
    rather than by summing four quarters so a missing 10-Q cannot drop events
    from the year.
    """
    k = fiscal_year_windows(filings)
    ev = events[events["event_date"].notna()].sort_values("event_date")
    out = pd.merge_asof(ev, k.sort_values("fy_end"),
                        left_on="event_date", right_on="fy_end",
                        by="gvkey", direction="forward")
    inside = out["fy_end"].notna() & (out["event_date"] > out["fy_start"])
    out.loc[~inside, "fy_accession"] = np.nan
    return out


# =============================================================
# STEP 3. Event-level loaders (dates kept; same rules as script 14)
# =============================================================
def load_warning_letter_events(s14, win) -> pd.DataFrame:
    """Device warning letters, one row per unique Case ID x gvkey."""
    ca = pd.read_csv(LETTERS_PATH, low_memory=False)
    dev = ca[ca["is_device"] & ca["is_warning_letter"]].copy()
    dev = dev.drop_duplicates("Case/Injunction ID")
    dev["event_date"] = pd.to_datetime(dev["action_taken_date"], errors="coerce")
    dev = dev[dev["event_date"].notna()]
    dev["year"] = dev["event_date"].dt.year.astype(int)
    dev["normalized_name"] = dev["company_name_clean"].map(s14.normalize_name)
    m = dev.merge(win, on="normalized_name", how="inner")
    m = m[(m["year"] >= m["valid_from_year"]) & (m["year"] <= m["valid_to_year"])]
    m = m.drop_duplicates(["gvkey", "Case/Injunction ID"])
    m["n"] = 1
    return m[["gvkey", "event_date", "year", "n"]]


def load_recall_events(s14, win) -> pd.DataFrame:
    """Part 806 recalls, one row per unique recall record (cfres_id) x gvkey."""
    rc = pd.read_csv(RECALLS_PATH, low_memory=False)
    init = pd.to_datetime(rc["event_date_initiated"], errors="coerce")
    post = pd.to_datetime(rc["event_date_posted"], errors="coerce")
    rc["event_date"] = init.fillna(post)
    rc = rc[rc["event_date"].notna() & rc["gvkey"].notna()].copy()
    rc["year"] = rc["event_date"].dt.year.astype(int)
    rc["gvkey"] = rc["gvkey"].astype("int64")
    rc["normalized_name"] = rc["recalling_firm"].map(s14.normalize_name)
    rc = rc.merge(win, on=["normalized_name", "gvkey"], how="left")
    rc["valid_from_year"] = rc["valid_from_year"].fillna(1900)
    rc["valid_to_year"] = rc["valid_to_year"].fillna(2099)
    rc = rc[(rc["year"] >= rc["valid_from_year"]) & (rc["year"] <= rc["valid_to_year"])]
    cls = rc["classification"].fillna("")
    rc["class_i"] = cls.eq("Class I").astype(int)
    rc["class_ii"] = cls.eq("Class II").astype(int)
    rc["class_iii"] = cls.eq("Class III").astype(int)
    rc = rc.drop_duplicates(["gvkey", "cfres_id"])
    rc["n"] = 1
    return rc[["gvkey", "event_date", "year", "n", "class_i", "class_ii", "class_iii"]]


def load_adverse_event_days(s14, win) -> pd.DataFrame:
    """
    Part 803 MAUDE reports collapsed to gvkey x DAY counts, read straight from
    script 11's per-partition cache. The cache (not a fresh `--resume` run) is
    used ON PURPOSE: it is the openFDA 2026-07-14 export the script-14 panel
    was built from; re-running script 11 today would pull a newer export and
    mix snapshots. The chunk count is checked so a partial cache cannot pass.
    """
    chunks = sorted(MAUDE_CACHE.glob("*.parquet"))
    print(f"    MAUDE cache: {len(chunks)} chunks (expected {MAUDE_EXPECTED_CHUNKS})")
    assert len(chunks) == MAUDE_EXPECTED_CHUNKS, "MAUDE cache is not the pinned snapshot"
    cols = ["gvkey", "date_received", "date_of_event", "link_tier", "manufacturer_d_name"]
    name_memo, parts, n_raw, n_empty = {}, [], 0, 0
    for c in chunks:
        # A partition in which no sample-firm report was found was cached as a
        # column-less empty frame; asking it for columns raises. Skip and count.
        if "gvkey" not in pq.read_schema(c).names:
            n_empty += 1
            continue
        ch = pd.read_parquet(c, columns=cols)
        n_raw += len(ch)
        rec = pd.to_datetime(ch["date_received"], format="%Y%m%d", errors="coerce")
        evt = pd.to_datetime(ch["date_of_event"], format="%Y%m%d", errors="coerce")
        ch["event_date"] = rec.fillna(evt)
        ch = ch[ch["event_date"].notna() & ch["gvkey"].notna()].copy()
        ch["year"] = ch["event_date"].dt.year.astype(int)
        ch["gvkey"] = ch["gvkey"].astype("int64")
        for nm in ch["manufacturer_d_name"].unique():
            if nm not in name_memo:
                name_memo[nm] = s14.normalize_name(nm)
        ch["normalized_name"] = ch["manufacturer_d_name"].map(name_memo)
        ch = ch.merge(win, on=["normalized_name", "gvkey"], how="left")
        ok = ((ch["year"] >= ch["valid_from_year"].fillna(1900))
              & (ch["year"] <= ch["valid_to_year"].fillna(2099)))
        ch = ch[ok]
        ch["tier_a"] = ch["link_tier"].eq("A_exact").astype(int)
        ch["tier_b"] = ch["link_tier"].eq("B_prefix").astype(int)
        parts.append(ch.groupby(["gvkey", "event_date", "year"])
                     .agg(n=("link_tier", "size"), tier_a=("tier_a", "sum"),
                          tier_b=("tier_b", "sum")).reset_index())
    out = (pd.concat(parts, ignore_index=True)
           .groupby(["gvkey", "event_date", "year"]).sum().reset_index())
    print(f"    MAUDE: {n_empty} empty chunks skipped")
    print(f"    MAUDE: {n_raw:,} cached reports ->{int(out['n'].sum()):,} "
          f"after date/window rules, {len(out):,} gvkey-days")
    return out


def reconcile_with_panel(events: dict, active: set) -> None:
    """
    Known-answer check: re-aggregating these event-level rows to gvkey-year and
    applying script 14's funda gate must reproduce the committed panel's
    n_events EXACTLY, for every cell. This is what licenses re-implementing the
    loaders with dates attached instead of reusing script 14's year-only ones.
    """
    panel = pd.read_csv(PANEL_PATH)
    for ev, df in events.items():
        mine = df.groupby(["gvkey", "year"])["n"].sum().reset_index()
        mine = mine[[k in active for k in zip(mine["gvkey"], mine["year"])]]
        ref = panel.loc[panel["event_type"] == ev, ["gvkey", "year", "n_events"]]
        cmp = mine.merge(ref, on=["gvkey", "year"], how="outer")
        bad = cmp[cmp["n"].fillna(-1) != cmp["n_events"].fillna(-1)]
        print(f"    reconcile {ev:<15}: {len(ref):,} panel cells, "
              f"{int(ref['n_events'].sum()):,} events -> mismatches: {len(bad)}")
        assert bad.empty, f"{ev}: event-level rows do not reproduce the panel\n{bad.head()}"


# =============================================================
# STEP 4. 8-K event disclosures
# =============================================================
def load_8k(filings: pd.DataFrame) -> pd.DataFrame:
    """
    Device 8-K dataset (script 16), one row per DOCUMENT (an 8-K form or one of
    its exhibits), so an accession can appear twice. Collapse to one row per
    8-K (accession) with each event flag = flagged in ANY of its documents.
    gvkey comes from the filing panel's CIK (one CIK per gvkey there); 8-Ks of
    filers outside the baseline panel cannot merge and are reported as such.
    """
    k = pd.read_csv(EIGHTK_PATH, low_memory=False)
    pe = pd.to_datetime(k["period_ending"], errors="coerce")
    k["event_date_8k"] = pe.fillna(pd.to_datetime(k["file_date"], errors="coerce"))
    flags = {ev: f"flag_{ev}" for ev in EVENT_TYPES}
    # Per-event DOCUMENT counts (a flag belongs to a document, so an 8-K whose
    # form is flagged but whose exhibit is not contributes one document).
    for ev, col in flags.items():
        k[f"ndoc_{ev}"] = k[col].astype(int)
    agg = {"cik": "first", "event_date_8k": "min", "document": "size"}
    agg.update({col: "max" for col in flags.values()})
    agg.update({f"ndoc_{ev}": "sum" for ev in flags})
    k = k.groupby("accession").agg(agg).reset_index().rename(columns={"document": "n_documents"})
    cik_map = (filings[["cik", "gvkey"]].drop_duplicates()
               .assign(cik=lambda d: d["cik"].astype("int64")))
    assert cik_map["cik"].is_unique
    k = k.merge(cik_map, on="cik", how="left")
    return k


# =============================================================
# STEP 5. Aggregate to the reporting quarter and merge onto the baseline
# =============================================================
KEY = ["gvkey", "reporting_year", "reporting_quarter"]


def to_quarter_counts(assigned: pd.DataFrame, rename: dict) -> pd.DataFrame:
    a = assigned[assigned["reporting_year"].notna()]
    return (a.groupby(KEY)[list(rename)].sum().rename(columns=rename).reset_index())


def build_combined(filings, ev_assigned, k_assigned, active, fy_assigned):
    combined = filings.copy()

    # Warning-letter data coverage (see WARNING_LETTER_DATA_START): 1 when the
    # whole reporting period / fiscal year lies inside FDA's letter data.
    combined["warning_letter_data_covered"] = (
        combined["period_start"] >= WARNING_LETTER_DATA_START).astype(int)
    fy_start = fiscal_year_windows(filings).set_index("fy_accession")["fy_start"]
    combined["fy_start"] = combined["accession"].map(fy_start)
    combined["fy_warning_letter_data_covered"] = (
        (combined["fy_start"] >= WARNING_LETTER_DATA_START).astype("Int64")
        .where(combined["form"] == "10-K"))

    # FISCAL-YEAR event counts, on 10-K rows only (blank on 10-Q rows): events
    # dated anywhere in the year the 10-K covers, for the yearly comparison.
    is_10k = combined["form"] == "10-K"
    for ev in EVENT_TYPES:
        a = fy_assigned[ev]
        fy = a[a["fy_accession"].notna()].groupby("fy_accession")["n"].sum()
        combined[f"fy_n_{ev}"] = (combined["accession"].map(fy).fillna(0)
                                  .where(is_10k).astype("Int64"))
        combined[f"fy_event_{ev}"] = ((combined[f"fy_n_{ev}"] > 0)
                                      .astype("Int64").where(is_10k))
    blocks = [
        to_quarter_counts(ev_assigned["warning_letter"], {"n": "n_warning_letter"}),
        to_quarter_counts(ev_assigned["recall"],
                          {"n": "n_recall", "class_i": "n_recall_class_i",
                           "class_ii": "n_recall_class_ii",
                           "class_iii": "n_recall_class_iii"}),
        to_quarter_counts(ev_assigned["adverse_event"],
                          {"n": "n_adverse_event", "tier_a": "n_mdr_tier_a",
                           "tier_b": "n_mdr_tier_b"}),
    ]
    k = k_assigned.copy()
    for ev in EVENT_TYPES:
        k[f"n_8k_{ev}"] = k[f"flag_{ev}"].astype(int)
    k["n_8k_any_event"] = 1
    blocks.append(to_quarter_counts(
        k, {c: c for c in [f"n_8k_{ev}" for ev in EVENT_TYPES] + ["n_8k_any_event"]}))

    n0 = len(combined)
    for b in blocks:
        combined = combined.merge(b, on=KEY, how="left", validate="one_to_one")
    assert len(combined) == n0, "merge changed the number of baseline filings"

    count_cols = [c for b in blocks for c in b.columns if c not in KEY]
    # A missing count is a TRUE ZERO: the filing is in the panel and no event
    # of that type was dated inside its reporting period.
    combined[count_cols] = combined[count_cols].fillna(0).astype(int)

    for ev in EVENT_TYPES:
        combined[f"event_{ev}"] = (combined[f"n_{ev}"] > 0).astype(int)
        combined[f"has_8k_{ev}"] = (combined[f"n_8k_{ev}"] > 0).astype(int)
    # "Any event" excludes nothing; but adverse-event reports arrive in nearly
    # every quarter for large firms, so a version without them is carried too.
    combined["event_any"] = combined[[f"event_{e}" for e in EVENT_TYPES]].max(axis=1)
    combined["event_letter_or_recall"] = combined[["event_warning_letter",
                                                   "event_recall"]].max(axis=1)
    combined["has_8k_any_event"] = (combined["n_8k_any_event"] > 0).astype(int)

    # Flag only (see header): script 14's "publicly traded that year" test.
    combined["compustat_active_year"] = [
        int(k_ in active) for k_ in zip(combined["gvkey"], combined["reporting_year"])]

    # MD&A substantive-disclosure indicators, the outcome the comparison needs.
    for ev in EVENT_TYPES:
        combined[f"mda_{ev}_substantive_flag"] = (
            combined[f"mda_{ev}_substantive"] > 0).astype(int)

    lead = (["gvkey", "cik", "company", "reporting_year", "reporting_quarter",
             "form", "accession", "filing_date", "report_date", "period_start",
             "period_end", "period_end_imputed", "compustat_active_year"]
            + [f"event_{e}" for e in EVENT_TYPES]
            + ["event_any", "event_letter_or_recall"] + count_cols
            + [f"has_8k_{e}" for e in EVENT_TYPES] + ["has_8k_any_event"]
            + [f"mda_{e}_substantive_flag" for e in EVENT_TYPES])
    rest = [c for c in combined.columns if c not in lead]
    combined = combined[lead + rest].sort_values(
        ["gvkey", "period_end"]).reset_index(drop=True)
    for c in ["filing_date", "report_date", "period_start", "period_end", "fy_start"]:
        combined[c] = combined[c].dt.date
    return combined


# =============================================================
# STEP 6. Descriptive tables (built once; rendered to Markdown and LaTeX)
# =============================================================
def build_tables(combined, ev_assigned, k8):
    fmt = lambda n: f"{int(n):,}"
    pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"
    is_k, is_q = combined["form"] == "10-K", combined["form"] == "10-Q"

    overview = pd.DataFrame([
        ("Filings = firm reporting quarters (rows)", fmt(len(combined))),
        ("  10-K", fmt(is_k.sum())),
        ("  10-Q", fmt(is_q.sum())),
        ("Firms (gvkey)", fmt(combined["gvkey"].nunique())),
        ("Reporting periods ending", f"{combined['period_end'].min()} to {combined['period_end'].max()}"),
        ("Filings with a parsed MD&A section", fmt(combined["has_mda"].sum())),
        ("Filings with a warning letter in the quarter", fmt(combined["event_warning_letter"].sum())),
        ("Filings with a recall in the quarter", fmt(combined["event_recall"].sum())),
        ("Filings with an adverse-event report in the quarter", fmt(combined["event_adverse_event"].sum())),
        ("Filings with no product event of any type in the quarter", fmt((combined["event_any"] == 0).sum())),
        ("Filings with an event 8-K in the quarter", fmt(combined["has_8k_any_event"].sum())),
    ], columns=["Statistic", "Value"])

    # ---- HEADLINE 1: unique filings with a SUBSTANTIVE MD&A mention ----
    rows = []
    for ev in EVENT_TYPES + ["__any__"]:
        if ev == "__any__":
            s = combined[[f"mda_{e}_substantive_flag" for e in EVENT_TYPES]].max(axis=1) == 1
            label = "Any of the three (each filing once)"
        else:
            s = combined[f"mda_{ev}_substantive_flag"] == 1
            label = EVENT_LABELS[ev]
        rows.append((label, fmt((s & is_k).sum()), fmt((s & is_q).sum()), fmt(s.sum()),
                     pct(s.sum(), len(combined))))
    substantive = pd.DataFrame(rows, columns=[
        "Event substantively discussed in MD&A", "10-K filings", "10-Q filings",
        "All filings", "Share of all filings"])

    # ---- The comparison the baseline design exists for ----
    rows = []
    for ev in EVENT_TYPES:
        # Warning letters: only filings whose period FDA's letter data covers.
        d = (combined[combined["warning_letter_data_covered"] == 1]
             if ev == "warning_letter" else combined)
        e1 = d[f"event_{ev}"] == 1
        s = d[f"mda_{ev}_substantive_flag"] == 1
        rows.append((EVENT_LABELS[ev] + (" *" if ev == "warning_letter" else ""),
                     fmt(e1.sum()), fmt((e1 & s).sum()),
                     pct((e1 & s).sum(), e1.sum()), fmt((~e1).sum()),
                     fmt((~e1 & s).sum()), pct((~e1 & s).sum(), (~e1).sum())))
    compare = pd.DataFrame(rows, columns=[
        "Event type", "Filings: event in quarter", "... substantive MD&A", "Rate",
        "Filings: no event in quarter", "... substantive MD&A ", "Rate "])

    # ---- HEADLINE 2: 8-Ks by event type ----
    in_base = k8["gvkey"].notna()
    merged = k8["reporting_year"].notna()
    rows = []
    for ev in EVENT_TYPES + ["__any__"]:
        f_ = pd.Series(True, index=k8.index) if ev == "__any__" else k8[f"flag_{ev}"].astype(bool)
        label = "Any event (each 8-K once)" if ev == "__any__" else EVENT_LABELS[ev]
        col = "has_8k_any_event" if ev == "__any__" else f"has_8k_{ev}"
        ndoc = k8["n_documents"].sum() if ev == "__any__" else k8[f"ndoc_{ev}"].sum()
        rows.append((label, fmt(ndoc), fmt(f_.sum()),
                     fmt((f_ & in_base).sum()), fmt((f_ & merged).sum()),
                     fmt(combined[col].sum())))
    eightk = pd.DataFrame(rows, columns=[
        "8-K event type", "Documents (forms + exhibits)", "Unique 8-Ks",
        "... at baseline-panel firms", "... merged to a reporting quarter",
        "Filings (quarters) with such an 8-K"])

    # ---- Yearly / 10-K-level version of the comparison ----
    k10 = combined[is_k]
    rows = []
    for ev in EVENT_TYPES:
        d = (k10[k10["fy_warning_letter_data_covered"] == 1]
             if ev == "warning_letter" else k10)
        e1 = d[f"fy_event_{ev}"] == 1
        s = d[f"mda_{ev}_substantive_flag"] == 1
        rows.append((EVENT_LABELS[ev] + (" *" if ev == "warning_letter" else ""),
                     fmt(e1.sum()), fmt((e1 & s).sum()),
                     pct((e1 & s).sum(), e1.sum()), fmt((~e1).sum()),
                     fmt((~e1 & s).sum()), pct((~e1 & s).sum(), (~e1).sum())))
    compare_10k = pd.DataFrame(rows, columns=[
        "Event type", "10-Ks: event in fiscal year", "... substantive MD&A", "Rate",
        "10-Ks: no event in fiscal year", "... substantive MD&A ", "Rate "])

    # ---- The EVENTS THEMSELVES: how many dated events of each type ----
    # Counted from the FDA source data, independent of any SEC filing. An
    # "event" = one warning letter (unique Case ID), one recall record
    # (cfres_id), one adverse-event report (MDR). "Distinct firm-dates" counts
    # each gvkey x calendar date once, however many events share that date.
    firms = set(combined["gvkey"])
    rows = []
    for ev in EVENT_TYPES:
        a_ = ev_assigned[ev]
        scopes = [("all gvkey-linked firms", a_),
                  ("firms in the 10-K/10-Q panel", a_[a_["gvkey"].isin(firms)]),
                  ("merged to a reporting quarter", a_[a_["reporting_year"].notna()])]
        for label, d in scopes:
            rows.append((f"{EVENT_LABELS[ev]} - {label}", fmt(d["n"].sum()),
                         fmt(d.groupby(["gvkey", "event_date"]).ngroups),
                         fmt(d["gvkey"].nunique()),
                         str(d["event_date"].min().date()),
                         str(d["event_date"].max().date())))
    event_dates = pd.DataFrame(rows, columns=[
        "Event type - scope", "Events", "Distinct firm-dates", "Firms", "First event date",
        "Last event date"])

    return [
        ("Overview", None, overview),
        ("Unique filings with a SUBSTANTIVE mention of each event in the MD&A",
         "Counts are unique filings (accession numbers) across the FULL baseline "
         "panel, MD&A section only (Item 7 in a 10-K, Item 2 in a 10-Q). "
         "'Substantive' = at least one MD&A occurrence tied to an actual event "
         "(past-tense receipt/action verb, definite reference, or specific date) "
         "and not hedged by a modal - script 17's definition. A filing can count "
         "under more than one event type.",
         substantive),
        ("Substantive MD&A disclosure: quarters WITH vs WITHOUT the event",
         "Raw rates, no controls - descriptive only. 'Event in quarter' = at "
         "least one event of that type dated inside the filing's own reporting "
         "period. Discussion in a no-event quarter is mostly the continuing "
         "discussion of an EARLIER quarter's event, so the right-hand rate is not "
         "a clean counterfactual. " + WL_NOTE,
         compare),
        ("Substantive MD&A disclosure at the YEARLY (10-K) level: fiscal years WITH vs WITHOUT the event",
         "10-K filings only. 'Event in fiscal year' = at least one event of that "
         "type dated anywhere inside the fiscal year the 10-K covers (previous "
         "10-K's period end to this one's; all four quarters, not just Q4). Raw "
         "rates, no controls. " + WL_NOTE,
         compare_10k),
        ("Event 8-Ks by event type",
         "Source: the device 8-K dataset (script 16), classified on the filing "
         "lead. One 8-K can carry several documents (form + exhibits) and more "
         "than one event flag. Only 8-Ks filed by firms in the 10-K/10-Q baseline "
         "panel can merge; an 8-K is placed by its reported event date.",
         eightk),
        ("Product event dates (the events themselves - no filings involved)",
         "Counted from the FDA source data. Event = one warning letter (unique "
         "Case ID, dated by action date), one recall record (dated when the firm "
         "initiated it), one adverse-event report (dated when FDA received it). "
         "'Distinct firm-dates' counts each firm x calendar date once. Events not "
         "merged belong to firms outside the 10-K/10-Q panel, predate the firm's "
         "first filing in it (the panel starts in 2005; MAUDE in 1991), postdate "
         "its last, or fall in a gap between filings.",
         event_dates),
    ]


WL_NOTE = ("* Warning-letter row uses only filings whose whole period falls on/after 2008-10-01, when FDA's letter data begins; earlier filings have letters UNOBSERVED, not absent, and are excluded rather than counted as no-event.")


# =============================================================
# STEP 7. Industry coverage: panel share of US medical-device market cap
# =============================================================
def load_universe_mktcap(panel_gvkeys) -> pd.DataFrame:
    """
    One row per firm in (US device universe) U (panel firms): gvkey, fic, sic,
    latest fiscal year-end on/after LIVE_CUTOFF, market cap and total assets
    ($M). Read from the gitignored cache if present, else pulled from WRDS
    (non-interactive; password from pgpass.conf) and cached.
    """
    if UNIVERSE_CACHE.exists():
        print(f"    using cached WRDS extract: {UNIVERSE_CACHE.name}")
        return pd.read_csv(UNIVERSE_CACHE, dtype={"gvkey": str, "sic": str},
                           parse_dates=["datadate"])

    import wrds
    print("    connecting to WRDS ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        sics = ",".join(f"'{x}'" for x in DEVICE_SICS)
        pkeys = ",".join(f"'{g}'" for g in sorted(set(panel_gvkeys)))
        comp = db.raw_sql(f"select gvkey, conm, fic, sic from comp.company "
                          f"where sic in ({sics}) or gvkey in ({pkeys})")
        keys = ",".join(f"'{g}'" for g in sorted(set(comp["gvkey"])))
        # Standard Compustat filters, as in scripts 09 and 14: without them
        # funda returns several rows per firm-year.
        live = db.raw_sql(f"""
            select gvkey, datadate, prcc_f*csho as mktcap, at
            from comp.funda
            where indfmt='INDL' and datafmt='STD' and popsrc='D' and consol='C'
              and datadate >= '{LIVE_CUTOFF}' and gvkey in ({keys})
        """, date_cols=["datadate"])
    finally:
        db.close()
    # Latest fiscal year-end WITH a computable market cap, one row per firm.
    live = (live.dropna(subset=["mktcap"]).sort_values("datadate")
                .groupby("gvkey").tail(1))
    out = comp.merge(live, on="gvkey", how="left")
    out.to_csv(UNIVERSE_CACHE, index=False)
    print(f"    pulled {len(out):,} firms -> {UNIVERSE_CACHE.relative_to(REPO_ROOT)}")
    return pd.read_csv(UNIVERSE_CACHE, dtype={"gvkey": str, "sic": str},
                       parse_dates=["datadate"])


def build_industry_share_block(combined: pd.DataFrame):
    """
    Panel firms' CURRENT market cap as a share of the US medical-device
    universe. Universe = US-incorporated (fic = USA) Compustat firms with
    primary SIC 3841-3845 and a computable market cap at their latest fiscal
    year-end on/after LIVE_CUTOFF (script 09's definition). A panel firm
    contributes to the share only if it is itself in that universe.
    """
    fmt = lambda n: f"{int(round(n)):,}"
    panel = {f"{int(g):06d}" for g in combined["gvkey"].unique()}
    u = load_universe_mktcap(panel)
    u["gvkey"] = u["gvkey"].str.zfill(6)
    u["in_panel"] = u["gvkey"].isin(panel)
    assert u["gvkey"].is_unique and u["in_panel"].sum() == len(panel)
    live = u["mktcap"].notna()
    is_dev = u["sic"].isin(DEVICE_SICS)
    is_us = u["fic"] == "USA"
    universe = u[live & is_dev & is_us]
    num = universe[universe["in_panel"]]
    share = num["mktcap"].sum() / universe["mktcap"].sum()

    # Why the other panel firms are not in the numerator - mutually exclusive.
    inp = u["in_panel"]
    n_no_cap = int((inp & ~live).sum())               # acquired / delisted / private
    n_non_dev = int((inp & live & ~is_dev).sum())     # pharma, diversified, retail ...
    n_foreign = int((inp & live & is_dev & ~is_us).sum())
    assert len(num) + n_no_cap + n_non_dev + n_foreign == int(inp.sum())

    rows = [
        ("Firms in the 10-K/10-Q panel", fmt(inp.sum())),
        ("  in the US medical-device universe (counted in the share)", fmt(len(num))),
        ("  no current market cap (acquired, delisted or private since)", fmt(n_no_cap)),
        ("  current market cap, but primary SIC outside 3841-3845", fmt(n_non_dev)),
        ("  device SIC, but incorporated outside the US", fmt(n_foreign)),
        ("US medical-device universe, firms", fmt(len(universe))),
        ("Panel firms as a share of universe firms",
         f"{100 * len(num) / len(universe):.1f}%"),
        ("Share of US medical-device market capitalization", f"{100 * share:.1f}%"),
        ("Market cap of panel firms in the universe ($M), mean", fmt(num["mktcap"].mean())),
        ("Market cap of panel firms in the universe ($M), median", fmt(num["mktcap"].median())),
        ("Total assets of panel firms in the universe ($M), mean", fmt(num["at"].mean())),
        ("Total assets of panel firms in the universe ($M), median", fmt(num["at"].median())),
        ("Fiscal year-ends at which market cap is measured",
         f"{universe['datadate'].min().date()} to {universe['datadate'].max().date()}"),
    ]
    note = (
        "Share = current market capitalization of the panel firms that are in "
        "the US medical-device universe, divided by the universe total. "
        "Universe: US-incorporated Compustat firms with primary SIC 3841-3845 "
        "and a computable market cap (fiscal year-end price x shares "
        f"outstanding) at their latest fiscal year-end on or after {LIVE_CUTOFF} "
        "- the definition used for Table 1 of 2026-07-06, recomputed here for "
        "the 10-K/10-Q panel. It is a CURRENT snapshot: panel firms acquired or "
        "delisted since they entered the sample contribute nothing, and neither "
        "do panel firms classified outside the device SIC codes or incorporated "
        "abroad, however large - so the share understates the panel's "
        "historical coverage. Source: Compustat (comp.company, comp.funda) via "
        "WRDS.")
    return ("Industry coverage: panel share of the US publicly traded "
            "medical-device industry", note,
            pd.DataFrame(rows, columns=["Statistic", "Value"]))


CAVEATS = [
    "Reporting year/quarter is the calendar year and quarter of the period end "
    "(snapped to the nearest month end) - a label for the firm's reporting "
    "period, not its own fiscal-quarter number. A 10-K row is the fiscal 4th "
    "quarter.",
    "An event is attached ONLY to the quarter it is dated in. Firms keep "
    "discussing a warning letter for years, so lagged/cumulative event "
    "indicators are needed before reading the no-event rate as a counterfactual.",
    "Adverse-event reports arrive almost every quarter at large firms, so "
    "event_adverse_event has little variation there; use the counts "
    "(n_adverse_event, and n_mdr_tier_a / n_mdr_tier_b separately - Tier B is "
    "parent-prefix name matching).",
    "Events use script 14's ownership-window gate but NOT its comp.funda gate; "
    "compustat_active_year flags the firm-years that gate would keep.",
    "Only Risk Factors and MD&A are parsed (script 17); event discussion "
    "located only in Legal Proceedings (Item 3) is missed.",
]


def write_markdown(blocks, path):
    lines = [f"# Descriptives - {DATASET_NAME}", "",
             f"Dataset: `data/{DATASET_NAME}.csv` - the full medical-device "
             "10-K/10-Q panel (one row per filing) with FDA product events and "
             "event 8-Ks merged in by gvkey x reporting year x reporting quarter. "
             "Built by `scripts/18_build_combined_filing_event_dataset.py`.", ""]
    for title, note, df in blocks:
        lines += [f"## {title}", ""]
        lines.append("| " + " | ".join(c.strip() for c in df.columns) + " |")
        lines.append("|" + "|".join([":---"] + ["---:"] * (df.shape[1] - 1)) + "|")
        for row in df.itertuples(index=False):
            lines.append("| " + " | ".join(str(v).replace("  ", "&nbsp;&nbsp;")
                                           for v in row) + " |")
        lines.append("")
        if note:
            lines += [f"*{note}*", ""]
    lines += ["## Caveats", ""] + [f"{i}. {c}" for i, c in enumerate(CAVEATS, 1)] + [""]
    path.write_text("\n".join(lines), encoding="utf-8")


def tex_escape(s) -> str:
    s = str(s)
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("_", r"\_"), ("#", r"\#"), ("$", r"\$")]:
        s = s.replace(a, b)
    return s


def write_pdf(blocks, pdf_path) -> bool:
    """Render the same tables with pdflatex (MiKTeX), as script 09 does."""
    body = []
    for title, note, df in blocks:
        ncol = df.shape[1]
        long_labels = df.iloc[:, 0].astype(str).str.len().max() > 45
        if ncol == 2:       # statistic/value tables: the label gets the room
            first_w = 0.66 if long_labels else 0.50
        else:               # wide tables: widen the label column only a little
            first_w = 0.36 if long_labels else 0.27
        # Budget 0.97 of the text width LESS the inter-column padding (2 x 3pt
        # per column, ~0.013 of the width each) so wide tables stay in the margin.
        other_w = (0.97 - 0.013 * ncol - first_w) / (ncol - 1)
        spec = (f"p{{{first_w:.2f}\\textwidth}}"
                + f">{{\\raggedleft\\arraybackslash}}p{{{other_w:.3f}\\textwidth}}" * (ncol - 1))
        body.append(f"\\subsection*{{{tex_escape(title)}}}")
        body.append(f"\\noindent\\begin{{tabular}}{{@{{}}{spec}@{{}}}}\\toprule")
        body.append(" & ".join(f"\\textbf{{{tex_escape(c.strip())}}}" for c in df.columns)
                    + r" \\ \midrule")
        for row in df.itertuples(index=False):
            cells = [tex_escape(v) for v in row]
            if str(row[0]).startswith("  "):
                cells[0] = r"\quad " + cells[0].strip()
            body.append(" & ".join(cells) + r" \\")
        body.append(r"\bottomrule\end{tabular}")
        if note:
            body.append(f"\\par\\smallskip\\noindent{{\\footnotesize\\textit{{{tex_escape(note)}}}}}")
    caveats = "\n".join(f"\\item {tex_escape(c)}" for c in CAVEATS)
    tex = (r"\documentclass[10pt]{article}" "\n"
           r"\usepackage[margin=0.9in]{geometry}\usepackage{booktabs,array}" "\n"
           r"\usepackage[T1]{fontenc}\usepackage{lmodern}\pagestyle{empty}" "\n"
           r"\begin{document}\setlength{\tabcolsep}{3pt}\small" "\n"
           f"\\section*{{Descriptives: {tex_escape(DATASET_NAME)}}}\n"
           r"\noindent The full medical-device 10-K/10-Q panel (one row per filing) "
           r"with FDA product events and event 8-Ks merged in by gvkey $\times$ "
           r"reporting year $\times$ reporting quarter.\par\noindent Source: "
           f"\\texttt{{data/{tex_escape(DATASET_NAME)}.csv}}.\\par\\noindent Built by "
           r"\texttt{scripts/18\_build\_combined\_filing\_event\_dataset.py}." "\n"
           + "\n".join(body)
           + "\n\\subsection*{Caveats}\\begin{enumerate}\\footnotesize\n"
           + caveats + "\n\\end{enumerate}\n\\end{document}\n")
    # Compile in a temp dir so no .tex/.aux/.log clutter lands in the repo.
    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / f"{pdf_path.stem}.tex"
        tex_path.write_text(tex, encoding="utf-8")
        res = subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_path.name],
                             cwd=tmp, capture_output=True, text=True)
        built = tex_path.with_suffix(".pdf")
        if res.returncode != 0 or not built.exists():
            print("    WARNING: pdflatex failed - PDF not produced.")
            print(res.stdout[-1500:])
            return False
        shutil.copyfile(built, pdf_path)
    return True


# =============================================================
# MAIN
# =============================================================
def main() -> int:
    s14 = load_script14()

    print("[1/6] Baseline: full 10-K/10-Q panel + reporting periods ...")
    filings = build_reporting_periods(load_filings())
    print(f"    {len(filings):,} filings, {filings['gvkey'].nunique()} firms")

    print("[2/6] Loading event-level data (with dates) ...")
    win = s14.load_ownership_windows()
    events = {"warning_letter": load_warning_letter_events(s14, win),
              "recall": load_recall_events(s14, win),
              "adverse_event": load_adverse_event_days(s14, win)}

    print("[3/6] Reconciling event-level rows against the script-14 panel ...")
    active, _ = s14.build_active_firm_years(pd.read_csv(FUNDA_PATH, low_memory=False))
    reconcile_with_panel(events, active)

    print("[4/6] Assigning events and 8-Ks to reporting quarters ...")
    ev_assigned = {ev: assign_to_period(df, filings, "event_date")
                   for ev, df in events.items()}
    k8 = load_8k(filings)
    k_in = k8[k8["gvkey"].notna()].copy()
    k_in["gvkey"] = k_in["gvkey"].astype("int64")
    k_in = assign_to_period(k_in, filings, "event_date_8k")
    k8 = k8.merge(k_in[["accession", "reporting_year", "reporting_quarter"]],
                  on="accession", how="left")
    # Ordering guarantee: every merged event precedes its filing's filing date.
    fd = filings.set_index(KEY)["filing_date"]
    for ev, a in ev_assigned.items():
        got = a[a["reporting_year"].notna()]
        filed = fd.reindex(pd.MultiIndex.from_frame(got[KEY].astype(int))).to_numpy()
        assert (got["event_date"].to_numpy() <= filed).all(), f"{ev}: event after filing"

    print("[5/6] Merging onto the baseline and saving ...")
    fy_assigned = {ev: assign_to_fiscal_year(df, filings) for ev, df in events.items()}
    combined = build_combined(filings, ev_assigned, k8, active, fy_assigned)
    assert len(combined) == len(filings) and combined["accession"].is_unique
    for ev in EVENT_TYPES:   # conservation: nothing lost or duplicated in the merge
        a = ev_assigned[ev]
        assert combined[f"n_{ev}"].sum() == a.loc[a["reporting_year"].notna(), "n"].sum()
    combined.to_csv(OUT_DATA, index=False)
    print(f"    -> {OUT_DATA.relative_to(REPO_ROOT)}  "
          f"({len(combined):,} rows x {combined.shape[1]} cols)")

    print("[6/6] Writing descriptives (md + pdf) ...")
    blocks = build_tables(combined, ev_assigned, k8)
    blocks.append(build_industry_share_block(combined))
    write_markdown(blocks, OUT_MD)
    print(f"    -> {OUT_MD.relative_to(REPO_ROOT)}")
    if write_pdf(blocks, OUT_PDF):
        print(f"    -> {OUT_PDF.relative_to(REPO_ROOT)}")
    for title, _, df in blocks:
        print(f"\n--- {title} ---\n{df.to_string(index=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
