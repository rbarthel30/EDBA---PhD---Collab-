# =============================================================
# Script: 08_device_universe_marketcap_share.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Size the treated sample against the industry: total equity market
#          capitalization of the US medical-device universe, and the share
#          of that value held by firms in our linked warning-letter sample.
# Inputs:  data/processed/fda_compliance_actions_<date>.csv                (script 03)
#          data/processed/compliance_actions_gvkey_crosswalk_full_<date>.csv (script 05)
#          WRDS tables comp.company, comp.funda                            (licensed; via WRDS)
# Outputs: output/tables/table03_device_universe_share_<date>.csv
#          output/tables/table03_device_universe_share_<date>.md
#
# DEFINITIONS (design choices, documented in the table notes):
#   * Universe = Compustat firms with primary SIC 3841-3845 (medical devices;
#     the project's stated industry filter), INCORPORATED in the US
#     (fic = 'USA'), with a market cap at their latest fiscal year-end no
#     older than ~one year. NOTE: incorporation-based "US" excludes inverted
#     firms (Medtronic is Irish-domiciled post-2015) — an alternative
#     headquarters-based universe would bring them back in.
#   * Treated = gvkey-linked device-warning-letter firms (crosswalk incl.
#     review-flagged matches; ownership windows respected). Treated firms
#     OUTSIDE the universe (foreign/inverted parents, diversified parents
#     with a non-device primary SIC, delisted/acquired firms) are reported
#     separately so they neither inflate nor silently vanish from the share.
#   * Market cap = prcc_f x csho ($ millions), standard INDL/STD/D/C screens.
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
DEVICE_SICS = ("3841", "3842", "3843", "3844", "3845")
# A "live" market cap must be from a fiscal year-end on/after this date —
# roughly the latest completed fiscal year for every reporting calendar.
LIVE_CUTOFF = "2024-06-30"


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching {pattern} — run the "
                                "upstream script first.")
    return Path(files[-1])


# =============================================================
# STEP 1. Treated firms: gvkeys of linked device-letter recipients
# =============================================================
def treated_gvkeys() -> set:
    ca = pd.read_csv(latest(str(PROCESSED_DIR / "fda_compliance_actions_*.csv")),
                     parse_dates=["action_taken_date"])
    cw = pd.read_csv(latest(str(PROCESSED_DIR /
                                "compliance_actions_gvkey_crosswalk_full_*.csv")),
                     dtype={"gvkey": str})
    dev = ca[ca["is_warning_letter"] & ca["is_device"]].copy()
    dev["year"] = dev["action_taken_date"].dt.year
    m = cw[cw["match_status"] == "matched"]
    ev = dev.merge(m, left_on="company_name_clean", right_on="company_name_fda")
    ev = ev[(ev["year"] >= ev["valid_from_year"])
            & (ev["year"] <= ev["valid_to_year"])]
    gv = set(ev["gvkey"].astype(str))
    print(f"[1/3] Treated (linked) device-letter firms: {len(gv)}")
    return gv


# =============================================================
# STEP 2. Universe and latest market caps from WRDS
# =============================================================
def fetch_universe_and_caps(treated: set):
    print("[2/3] Pulling comp.company + comp.funda from WRDS ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        sics = ",".join(f"'{s}'" for s in DEVICE_SICS)
        uni = db.raw_sql(
            f"select gvkey, conm, sic, fic from comp.company "
            f"where sic in ({sics})")
        keys = ",".join(f"'{g}'" for g in
                        sorted(set(uni["gvkey"].astype(str)) | treated))
        funda = db.raw_sql(f"""
            select gvkey, datadate, prcc_f, csho
            from comp.funda
            where indfmt='INDL' and datafmt='STD'
              and popsrc='D' and consol='C'
              and datadate >= '{LIVE_CUTOFF}'
              and gvkey in ({keys})
        """, date_cols=["datadate"])
    finally:
        db.close()

    uni["gvkey"] = uni["gvkey"].astype(str)
    funda["gvkey"] = funda["gvkey"].astype(str)
    funda["mktcap"] = funda["prcc_f"] * funda["csho"]
    # One market cap per firm: its most recent fiscal year-end.
    live = (funda.dropna(subset=["mktcap"])
                 .sort_values("datadate").groupby("gvkey").tail(1)
                 .set_index("gvkey")["mktcap"])
    return uni, live


# =============================================================
# STEP 3. Build and write the table
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    treated = treated_gvkeys()
    uni, live = fetch_universe_and_caps(treated)

    us_uni = uni[uni["fic"] == "USA"].copy()
    us_uni["mktcap"] = us_uni["gvkey"].map(live)
    uni_live = us_uni.dropna(subset=["mktcap"])
    total = uni_live["mktcap"].sum()

    t_in = uni_live[uni_live["gvkey"].isin(treated)]
    t_out = treated - set(uni_live["gvkey"])
    t_out_live = live[live.index.isin(t_out)]

    fmt = lambda v: round(float(v), 0)
    table = pd.DataFrame([
        {"Group": "US medical-device universe (SIC 3841-3845, US-incorporated)",
         "Firms": len(uni_live), "Market cap ($M)": fmt(total),
         "Share of universe value": "100%", "Share of universe firms": "100%"},
        {"Group": "  of which: treated (linked FDA device warning letter)",
         "Firms": len(t_in), "Market cap ($M)": fmt(t_in["mktcap"].sum()),
         "Share of universe value": f"{100 * t_in['mktcap'].sum() / total:.1f}%",
         "Share of universe firms": f"{100 * len(t_in) / len(uni_live):.1f}%"},
        {"Group": "Treated firms outside the universe, still listed",
         "Firms": len(t_out_live), "Market cap ($M)": fmt(t_out_live.sum()),
         "Share of universe value": "—", "Share of universe firms": "—"},
        {"Group": "Treated firms without a live market cap (delisted/acquired)",
         "Firms": len(t_out) - len(t_out_live), "Market cap ($M)": "—",
         "Share of universe value": "—", "Share of universe firms": "—"},
    ])

    csv_path = TABLES_DIR / f"table03_device_universe_share_{snapshot_date}.csv"
    md_path = csv_path.with_suffix(".md")
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")

    notes = (
        "\nNotes:\n"
        "- Universe: Compustat firms with primary SIC 3841-3845, incorporated in "
        "the US (fic = 'USA'), with a market cap (prcc_f x csho, $ millions) at "
        f"their latest fiscal year-end on/after {LIVE_CUTOFF}. Incorporation-based "
        "'US' excludes inverted firms — notably Medtronic (Irish-domiciled since "
        "2015), which is treated but appears in the outside-universe row.\n"
        "- Treated: firms linked to a device-classified FDA warning letter "
        "(2008-2026) in the project crosswalk, inclusive of review-flagged "
        "matches, ownership windows respected.\n"
        "- 'Outside the universe, still listed': foreign/inverted parents (e.g., "
        "Siemens, Medtronic) and diversified parents whose primary SIC is not "
        "medical devices (e.g., 3M, Cardinal Health).\n"
        "- The treated value share is conservative: Abbott Laboratories (the "
        "largest universe firm) is counted as untreated because its 'Abbott "
        "Medical' letters await a manual crosswalk override.\n"
        f"- Snapshot {snapshot_date}; scripts 03/05/08.\n")
    md = ("# Table 3. Treated firms' share of US medical-device market value\n\n"
          + table.to_markdown(index=False) + "\n" + notes)
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
