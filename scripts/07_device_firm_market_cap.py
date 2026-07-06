# =============================================================
# Script: 07_device_firm_market_cap.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Measure the SIZE (equity market capitalization) of the public
#          medical-device firms that receive FDA warning letters, and produce
#          descriptive statistics. Market cap is measured at the LAST FISCAL
#          YEAR-END BEFORE the letter, so it reflects firm size going INTO
#          the treatment event (a post-letter measure would be contaminated
#          by the market's reaction to the letter itself).
# Inputs:  data/processed/fda_compliance_actions_<date>.csv               (script 03)
#          data/processed/compliance_actions_gvkey_crosswalk_full_<date>.csv (script 05)
#          WRDS table comp.funda                                          (licensed; via WRDS)
# Outputs: data/processed/device_letter_marketcap_<date>.csv   (letter-level panel)
#          output/tables/table02_device_marketcap_descriptives_<date>.csv
#          output/tables/table02_device_marketcap_descriptives_<date>.md
#
# DESIGN CHOICES:
#   * Sample = device-classified warning letters whose recipient links to a
#     gvkey in the FULL crosswalk (script 05), ownership windows respected.
#     Review-flagged matches are INCLUDED (consistent with Table 1) — drop
#     them later if manual review rejects them.
#   * Market cap = prcc_f * csho from Compustat Fundamentals Annual
#     (fiscal-year-end close price x common shares outstanding, $ millions).
#     Standard Compustat screens: INDL / STD / D / C.
#   * The matched fiscal year-end must be within 18 months BEFORE the letter
#     date — older data is stale (delisted firms, reporting gaps) and is
#     treated as missing rather than silently used.
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import glob
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import wrds

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
TABLES_DIR = REPO_ROOT / "output" / "tables"

WRDS_USERNAME = os.environ.get("WRDS_USERNAME", "rxb1406")

# Maximum staleness of the pre-letter fiscal year-end (months).
MAX_LAG_MONTHS = 18


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching {pattern} — run the "
                                "upstream script first.")
    return Path(files[-1])


# =============================================================
# STEP 1. Build the linked device-letter event sample
# =============================================================
def build_event_sample() -> pd.DataFrame:
    """
    One row per (device letter x linked gvkey): the letters that will get a
    market-cap measurement. Ownership windows enforced, as in script 06.
    """
    ca = pd.read_csv(latest(str(PROCESSED_DIR / "fda_compliance_actions_*.csv")),
                     parse_dates=["action_taken_date"])
    cw = pd.read_csv(latest(str(PROCESSED_DIR /
                                "compliance_actions_gvkey_crosswalk_full_*.csv")),
                     dtype={"gvkey": str})

    dev = ca[ca["is_warning_letter"] & ca["is_device"]].copy()
    dev["year"] = dev["action_taken_date"].dt.year

    matched = cw[cw["match_status"] == "matched"][
        ["company_name_fda", "gvkey", "company_name_compustat",
         "review_suggested", "valid_from_year", "valid_to_year"]]
    ev = dev.merge(matched, left_on="company_name_clean",
                   right_on="company_name_fda", how="inner")
    ev = ev[(ev["year"] >= ev["valid_from_year"])
            & (ev["year"] <= ev["valid_to_year"])]

    # One row per letter x firm (a letter can span several establishment rows).
    ev = (ev.sort_values("action_taken_date")
            .drop_duplicates(["Case/Injunction ID", "gvkey"]))
    print(f"[1/4] Event sample: {len(ev):,} linked device letters, "
          f"{ev['gvkey'].nunique()} unique firms "
          f"({int(ev['review_suggested'].sum())} letters at review-flagged matches)")
    return ev[["Case/Injunction ID", "action_taken_date", "year",
               "company_name_clean", "gvkey", "company_name_compustat",
               "review_suggested"]]


# =============================================================
# STEP 2. Pull Compustat fundamentals (market cap inputs) from WRDS
# =============================================================
def fetch_funda(gvkeys: list) -> pd.DataFrame:
    """
    Fiscal-year-end price and shares outstanding for the sample firms,
    2007 onward (a letter in Oct 2008 can look back to a FY2007 year-end).
    """
    print(f"[2/4] Pulling comp.funda for {len(gvkeys)} gvkeys from WRDS ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        keys = ",".join(f"'{g}'" for g in gvkeys)
        funda = db.raw_sql(f"""
            select gvkey, datadate, fyear, prcc_f, csho, at
            from comp.funda
            where indfmt = 'INDL' and datafmt = 'STD'
              and popsrc = 'D' and consol = 'C'
              and datadate >= '2007-01-01'
              and gvkey in ({keys})
        """, date_cols=["datadate"])
    finally:
        db.close()

    funda["mktcap"] = funda["prcc_f"] * funda["csho"]   # $ millions
    funda = funda.dropna(subset=["mktcap"])
    print(f"    {len(funda):,} firm-year observations with market cap "
          f"({funda['gvkey'].nunique()} firms have at least one)")
    return funda[["gvkey", "datadate", "fyear", "mktcap", "at"]]


# =============================================================
# STEP 3. Match each letter to its last pre-letter fiscal year-end
# =============================================================
def attach_marketcap(ev: pd.DataFrame, funda: pd.DataFrame) -> pd.DataFrame:
    """
    merge_asof: for each letter, the most recent fiscal year-end strictly
    before the letter date, within MAX_LAG_MONTHS.
    """
    ev = ev.sort_values("action_taken_date").copy()
    funda = funda.sort_values("datadate").copy()
    # WRDS returns pandas' string dtype; the CSV side is plain object —
    # merge_asof requires identical key dtypes.
    ev["gvkey"] = ev["gvkey"].astype(str)
    funda["gvkey"] = funda["gvkey"].astype(str)
    out = pd.merge_asof(
        ev, funda,
        left_on="action_taken_date", right_on="datadate",
        by="gvkey", allow_exact_matches=False,
        tolerance=pd.Timedelta(days=int(MAX_LAG_MONTHS * 30.44)))
    out["has_mktcap"] = out["mktcap"].notna()
    n = int(out["has_mktcap"].sum())
    print(f"[3/4] Market cap attached for {n:,} of {len(out):,} letters "
          f"({out.loc[out['has_mktcap'], 'gvkey'].nunique()} firms). "
          "Misses are typically foreign parents or delisted/stale records.")
    return out


# =============================================================
# STEP 4. Descriptive statistics
# =============================================================
def describe(x: pd.Series) -> dict:
    q = x.quantile
    return {
        "N": int(x.notna().sum()),
        "Mean": x.mean(), "SD": x.std(),
        "Min": x.min(), "P10": q(.10), "P25": q(.25),
        "Median": q(.50), "P75": q(.75), "P90": q(.90),
        "Max": x.max(),
    }


def main() -> None:
    snapshot_date = date.today().isoformat()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    ev = build_event_sample()
    funda = fetch_funda(sorted(ev["gvkey"].unique()))
    panel = attach_marketcap(ev, funda)

    panel_path = (PROCESSED_DIR /
                  f"device_letter_marketcap_{snapshot_date}.csv")
    panel.to_csv(panel_path, index=False, encoding="utf-8-sig")

    ok = panel[panel["has_mktcap"]]
    # Letter-event level: every letter is one observation (a firm with three
    # letters appears three times — this describes the size of the TREATED
    # events). Firm level: one observation per firm (its market cap at its
    # FIRST letter) — this describes the treated FIRMS.
    firm_first = (ok.sort_values("action_taken_date")
                    .drop_duplicates("gvkey"))

    rows = {
        "Letter-event level ($M)": describe(ok["mktcap"]),
        "Firm level, at first letter ($M)": describe(firm_first["mktcap"]),
    }
    table = pd.DataFrame(rows).T.reset_index(names="Unit of observation")
    for c in table.columns[2:]:
        table[c] = table[c].map(lambda v: round(float(v), 1))
    table["N"] = table["N"].astype(int)

    csv_path = (TABLES_DIR /
                f"table02_device_marketcap_descriptives_{snapshot_date}.csv")
    md_path = csv_path.with_suffix(".md")
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")

    notes = (f"\nNotes:\n"
             f"- Sample: device-classified FDA warning letters (Oct 2008 - Jul 2026) "
             f"linked to a Compustat gvkey (crosswalk incl. review-flagged matches; "
             f"ownership windows respected).\n"
             f"- Market cap = prcc_f x csho ($ millions) at the last fiscal year-end "
             f"strictly before the letter date (max lag {MAX_LAG_MONTHS} months).\n"
             f"- {len(panel) - len(ok)} of {len(panel)} linked letters have no usable "
             f"market cap (foreign parents without Compustat NA coverage, delistings, "
             f"reporting gaps).\n"
             f"- Snapshot {snapshot_date}.\n")
    md = ("# Table 2. Market capitalization of device warning-letter firms\n\n"
          + table.to_markdown(index=False) + "\n" + notes)
    md_path.write_text(md, encoding="utf-8")

    print("[4/4] Written:")
    print(f"  {panel_path.relative_to(REPO_ROOT)}")
    print(f"  {csv_path.relative_to(REPO_ROOT)}")
    print(f"  {md_path.relative_to(REPO_ROOT)}")
    print()
    print(table.to_string(index=False))
    print()
    print("Largest / smallest treated firms (at first letter):")
    show = firm_first.sort_values("mktcap", ascending=False)
    cols = ["company_name_compustat", "mktcap", "year"]
    print(show.head(10)[cols].to_string(index=False))
    print("   ...")
    print(show.tail(5)[cols].to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
