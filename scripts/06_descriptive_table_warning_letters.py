# =============================================================
# Script: 06_descriptive_table_warning_letters.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Produce the first descriptive table of the warning-letter sample:
#          by calendar year, the number of FDA warning letters (tobacco
#          excluded upstream by script 03), the device / drug / biologic
#          subsets, and how many letters and firms are successfully linked
#          to a Compustat gvkey (INCLUSIVE of matches flagged for manual
#          review — the flag marks them for checking, it does not exclude
#          them here).
# Inputs:  data/processed/fda_compliance_actions_<date>.csv            (script 03)
#          data/processed/compliance_actions_gvkey_crosswalk_full_<date>.csv (script 05)
# Outputs: output/tables/table01_warning_letter_descriptives_<date>.csv
#          output/tables/table01_warning_letter_descriptives_<date>.md
#
# COUNTING RULES (documented in the table notes too):
#   * Letters are counted by unique Case/Injunction ID — one letter can span
#     several rows (establishments / product types).
#   * A letter with both a Devices row and a Drugs row counts in BOTH the
#     device and drug columns, but only once in the totals.
#   * gvkey links respect ownership windows: a letter is "linked" only when
#     its year falls inside the crosswalk row's valid_from/valid_to window
#     (e.g., letters to Genzyme in 2009 link to Genzyme's gvkey; the same
#     name in 2012 links to Sanofi's).
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import glob
import sys
from datetime import date
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
TABLES_DIR = REPO_ROOT / "output" / "tables"


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching {pattern} — run the "
                                "upstream script first.")
    return Path(files[-1])


# =============================================================
# STEP 1. Load letters and crosswalk
# =============================================================
def load_inputs():
    ca_path = latest(str(PROCESSED_DIR / "fda_compliance_actions_*.csv"))
    cw_path = latest(str(PROCESSED_DIR /
                         "compliance_actions_gvkey_crosswalk_full_*.csv"))
    ca = pd.read_csv(ca_path, parse_dates=["action_taken_date"])
    cw = pd.read_csv(cw_path, dtype={"gvkey": str})
    wl = ca[ca["is_warning_letter"]].copy()
    wl["year"] = wl["action_taken_date"].dt.year
    print(f"[1/3] Loaded {len(wl):,} warning-letter rows from {ca_path.name}")
    print(f"      and {len(cw):,} crosswalk rows from {cw_path.name}")
    return wl, cw


# =============================================================
# STEP 2. Link letters to gvkeys (window-respecting)
# =============================================================
def link_letters(wl: pd.DataFrame, cw: pd.DataFrame) -> pd.DataFrame:
    """
    Return the warning-letter rows that link to a gvkey. Inclusive of
    review-flagged matches (review_suggested marks rows for later manual
    checking; it does not remove them from these counts). Ownership windows
    are enforced: the letter year must fall inside [valid_from, valid_to].
    """
    matched = cw[cw["match_status"] == "matched"][
        ["company_name_fda", "gvkey", "valid_from_year", "valid_to_year"]]
    linked = wl.merge(matched, left_on="company_name_clean",
                      right_on="company_name_fda", how="inner")
    linked = linked[(linked["year"] >= linked["valid_from_year"])
                    & (linked["year"] <= linked["valid_to_year"])]
    return linked


# =============================================================
# STEP 3. Build the by-year table
# =============================================================
def build_table(wl: pd.DataFrame, linked: pd.DataFrame) -> pd.DataFrame:
    """
    One row per calendar year plus a Total row. All letter counts are unique
    Case/Injunction IDs within the group.
    """
    def uniq_cases(df):
        return df["Case/Injunction ID"].nunique()

    rows = []
    years = sorted(wl["year"].unique())
    for yr in years:
        w = wl[wl["year"] == yr]
        l = linked[linked["year"] == yr]
        rows.append({
            "Year": int(yr),
            "Warning letters": uniq_cases(w),
            "Device letters": uniq_cases(w[w["is_device"]]),
            "Drug letters": uniq_cases(w[w["is_drug"]]),
            "Biologic letters": uniq_cases(w[w["is_biologic"]]),
            "Letters linked to gvkey": uniq_cases(l),
            "Unique gvkey firms": l["gvkey"].nunique(),
        })
    rows.append({
        "Year": "Total",
        "Warning letters": uniq_cases(wl),
        "Device letters": uniq_cases(wl[wl["is_device"]]),
        "Drug letters": uniq_cases(wl[wl["is_drug"]]),
        "Biologic letters": uniq_cases(wl[wl["is_biologic"]]),
        "Letters linked to gvkey": uniq_cases(linked),
        # Total = distinct firms over the whole sample (NOT the column sum:
        # a firm receiving letters in several years is one firm).
        "Unique gvkey firms": linked["gvkey"].nunique(),
    })
    return pd.DataFrame(rows)


NOTES = """Notes:
- Source: FDA Data Dashboard compliance actions (scripts 03-05), snapshot {snap}. Tobacco-retailer letters are excluded upstream by script 03.
- Letters are counted by unique Case/Injunction ID. A letter spanning several product types (e.g., Devices and Drugs) counts once in 'Warning letters' but appears in each product column, so product columns need not sum to the total.
- 'Letters linked to gvkey' / 'Unique gvkey firms' are restricted to the analysis universe (device, drug, or biologic letters). They count links INCLUSIVE of matches flagged for manual review (review_suggested = True in the crosswalk), and respect ownership windows (a letter links only to the firm that owned the recipient in the letter year).
- {yfirst} and {ylast} are partial years (coverage starts 2008-10-01; snapshot taken {snap}).
"""


# =============================================================
# STEP 4. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    wl, cw = load_inputs()
    print("[2/3] Linking letters to gvkeys (window-respecting) ...")
    # Link columns are restricted to the analysis universe (device / drug /
    # biologic letters) — a food-firm match would inflate the usable sample.
    linked = link_letters(wl[wl["is_medtech_pharma"]], cw)
    table = build_table(wl, linked)

    csv_path = (TABLES_DIR /
                f"table01_warning_letter_descriptives_{snapshot_date}.csv")
    md_path = csv_path.with_suffix(".md")
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")

    notes = NOTES.format(snap=snapshot_date,
                         yfirst=int(wl['year'].min()),
                         ylast=int(wl['year'].max()))
    md = ("# Table 1. FDA Warning Letters — descriptive counts by year\n\n"
          + table.to_markdown(index=False) + "\n\n" + notes)
    md_path.write_text(md, encoding="utf-8")

    print("[3/3] Written:")
    print(f"  {csv_path.relative_to(REPO_ROOT)}")
    print(f"  {md_path.relative_to(REPO_ROOT)}")
    print()
    print(table.to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
