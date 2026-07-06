# =============================================================
# Script: 09_device_sample_descriptives.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: (1) Build and SAVE the analysis sub-dataset: every medical-device
#          warning letter whose recipient is linked to a Compustat gvkey,
#          enriched with the firm's market cap and total assets measured at
#          the last fiscal year-end BEFORE the letter (size going into the
#          event, uncontaminated by the market's reaction to it).
#          (2) Produce the paper's descriptive table (Table 1) for this
#          sub-dataset — Markdown, CSV, LaTeX, and compiled PDF.
# Inputs:  data/processed/fda_compliance_actions_<date>.csv                 (script 03)
#          data/processed/compliance_actions_gvkey_crosswalk_full_<date>.csv (script 05)
#          WRDS tables comp.funda, comp.company                             (licensed; via WRDS)
# Outputs: data/processed/device_letters_linked_<date>.csv    (the sub-dataset)
#          output/tables/table1_device_sample_descriptives_<date>.{md,csv,tex,pdf}
#
# DESIGN CHOICES:
#   * Sample = device-classified warning letters linked to a gvkey in the
#     full crosswalk (script 05), INCLUSIVE of review-flagged matches;
#     ownership windows respected (letter year inside [valid_from, valid_to]).
#     One row per letter x firm; letters counted by unique Case/Injunction ID.
#   * ACTIVE-AT-LETTER-DATE requirement (Ryan, 2026-07-06): the sample keeps
#     only letters whose firm has an ACTIVE Compustat record when the letter
#     arrives — operationalized as a non-missing market cap at the last
#     fiscal year-end before the letter (within the staleness window). This
#     drops linked-but-unmeasurable letters (foreign parents without US
#     fundamentals, letters outside the firm's Compustat coverage) so every
#     firm in the dataset and the table carries usable pre-letter data.
#   * Market cap = prcc_f x csho; total assets = at (both $ millions,
#     comp.funda, INDL/STD/D/C screens), at the last fiscal year-end strictly
#     before the letter, within an 18-month staleness window.
#   * Universe share = treated firms' CURRENT market cap as a fraction of the
#     US medical-device universe (primary SIC 3841-3845, US-incorporated,
#     latest fiscal year-end >= 2024-06-30) — the scale statistic, computed
#     as in script 08.
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import glob
import os
import subprocess
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
LIVE_CUTOFF = "2024-06-30"     # "current" market cap = latest FY-end after this
MAX_LAG_MONTHS = 18            # staleness limit for pre-letter fundamentals


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching {pattern} — run the "
                                "upstream script first.")
    return Path(files[-1])


# =============================================================
# STEP 1. Build the linked device-letter sub-dataset
# =============================================================
def build_subdataset() -> pd.DataFrame:
    ca = pd.read_csv(latest(str(PROCESSED_DIR / "fda_compliance_actions_*.csv")),
                     parse_dates=["action_taken_date"])
    cw = pd.read_csv(latest(str(PROCESSED_DIR /
                                "compliance_actions_gvkey_crosswalk_full_*.csv")),
                     dtype={"gvkey": str})

    dev = ca[ca["is_warning_letter"] & ca["is_device"]].copy()
    dev["year"] = dev["action_taken_date"].dt.year

    matched = cw[cw["match_status"] == "matched"][
        ["company_name_fda", "gvkey", "company_name_compustat",
         "match_source", "review_suggested", "valid_from_year", "valid_to_year"]]
    sub = dev.merge(matched, left_on="company_name_clean",
                    right_on="company_name_fda", how="inner")
    sub = sub[(sub["year"] >= sub["valid_from_year"])
              & (sub["year"] <= sub["valid_to_year"])]

    # One row per letter x firm (letters can span establishment rows).
    sub = (sub.sort_values("action_taken_date")
              .drop_duplicates(["Case/Injunction ID", "gvkey"]))
    sub = sub[["Case/Injunction ID", "action_taken_date", "year",
               "company_name_clean", "State", "Country/Area",
               "gvkey", "company_name_compustat", "match_source",
               "review_suggested"]].rename(
        columns={"Case/Injunction ID": "case_id",
                 "State": "state", "Country/Area": "country"})
    print(f"[1/4] Sub-dataset: {sub['case_id'].nunique():,} linked device "
          f"letters, {sub['gvkey'].nunique()} unique firms")
    return sub


# =============================================================
# STEP 2. Pre-letter fundamentals + universe share from WRDS
# =============================================================
def fetch_wrds(sub: pd.DataFrame):
    print("[2/4] Pulling comp.funda and comp.company from WRDS ...")
    db = wrds.Connection(wrds_username=WRDS_USERNAME)
    try:
        keys = ",".join(f"'{g}'" for g in sorted(sub["gvkey"].unique()))
        funda = db.raw_sql(f"""
            select gvkey, datadate, prcc_f, csho, at
            from comp.funda
            where indfmt='INDL' and datafmt='STD' and popsrc='D' and consol='C'
              and datadate >= '2007-01-01' and gvkey in ({keys})
        """, date_cols=["datadate"])
        sics = ",".join(f"'{s}'" for s in DEVICE_SICS)
        uni = db.raw_sql(f"select gvkey, fic from comp.company "
                         f"where sic in ({sics})")
        ukeys = ",".join(f"'{g}'" for g in
                         sorted(set(uni["gvkey"].astype(str))
                                | set(sub["gvkey"].astype(str))))
        live = db.raw_sql(f"""
            select gvkey, datadate, prcc_f*csho as mktcap
            from comp.funda
            where indfmt='INDL' and datafmt='STD' and popsrc='D' and consol='C'
              and datadate >= '{LIVE_CUTOFF}' and gvkey in ({ukeys})
        """, date_cols=["datadate"])
    finally:
        db.close()
    for df in (funda, uni, live):
        df["gvkey"] = df["gvkey"].astype(str)
    return funda, uni, live


def attach_fundamentals(sub: pd.DataFrame, funda: pd.DataFrame) -> pd.DataFrame:
    """Last pre-letter fiscal year-end market cap and total assets."""
    funda = funda.copy()
    funda["mktcap"] = funda["prcc_f"] * funda["csho"]
    funda = (funda.dropna(subset=["mktcap", "at"], how="all")
                  .sort_values("datadate"))
    sub = sub.sort_values("action_taken_date").copy()
    sub["gvkey"] = sub["gvkey"].astype(str)
    out = pd.merge_asof(
        sub, funda[["gvkey", "datadate", "mktcap", "at"]],
        left_on="action_taken_date", right_on="datadate",
        by="gvkey", allow_exact_matches=False,
        tolerance=pd.Timedelta(days=int(MAX_LAG_MONTHS * 30.44)))
    return out.rename(columns={"datadate": "preletter_fye",
                               "mktcap": "mktcap_preletter",
                               "at": "assets_preletter"})


def universe_share(sub: pd.DataFrame, uni: pd.DataFrame, live: pd.DataFrame):
    """Treated firms' current market cap / US device-universe market cap."""
    lk = (live.dropna(subset=["mktcap"])
              .sort_values("datadate").groupby("gvkey").tail(1)
              .set_index("gvkey")["mktcap"])
    us = uni[uni["fic"] == "USA"].copy()
    us["mktcap"] = us["gvkey"].map(lk)
    us = us.dropna(subset=["mktcap"])
    treated = set(sub["gvkey"])
    t_in = us[us["gvkey"].isin(treated)]
    return t_in["mktcap"].sum() / us["mktcap"].sum(), len(t_in), len(us)


# =============================================================
# STEP 3. The descriptive table
# =============================================================
def money(v):
    return f"{v:,.0f}"


def build_rows(sub, share, n_in, n_uni):
    firm = sub.sort_values("action_taken_date").drop_duplicates("gvkey")
    mc, ta = firm["mktcap_preletter"].dropna(), firm["assets_preletter"].dropna()
    period = (f"{sub['action_taken_date'].min():%B %Y} – "
              f"{sub['action_taken_date'].max():%B %Y}")
    return [
        ("Number of warning letters", f"{sub['case_id'].nunique():,}"),
        ("Number of unique firms", f"{sub['gvkey'].nunique():,}"),
        ("Firm market capitalization ($M), mean", money(mc.mean())),
        ("Firm market capitalization ($M), median", money(mc.median())),
        ("Firm total assets ($M), mean", money(ta.mean())),
        ("Firm total assets ($M), median", money(ta.median())),
        ("Share of US medical-device market capitalization", f"{100*share:.1f}%"),
        ("Sample period", period),
    ], len(mc), len(ta), n_in, n_uni


NOTES = ("This table describes the analysis sample: FDA warning letters "
         "classified by the FDA as medical-device actions whose recipient is "
         "linked to a Compustat firm (gvkey) with an active record as of the "
         "letter date — a non-missing market capitalization at the last "
         "fiscal year-end before the letter (within 18 months). Links come "
         "from the project crosswalk, inclusive of matches flagged for "
         "manual review; ownership windows are respected, so a letter links "
         "to the firm that owned the recipient in the letter year. Letters "
         "are counted by unique FDA Case/Injunction ID. Market "
         "capitalization (fiscal year-end close price times common shares "
         "outstanding) and total assets are measured at the last fiscal "
         "year-end before the firm's first letter, in $ millions"
         "{ta_gap}. The market-cap share is the sample firms' current "
         "market capitalization as a fraction of the US medical-device "
         "universe: {nin} sample firms of the {nuni} US-incorporated "
         "Compustat firms with primary SIC 3841–3845 and a market cap at "
         "their latest fiscal year-end; sample firms delisted or acquired "
         "since their letter no longer contribute. Sources: FDA Data "
         "Dashboard compliance actions; Compustat via WRDS.")


def write_outputs(rows, notes, snapshot_date):
    md_path = TABLES_DIR / f"table1_device_sample_descriptives_{snapshot_date}.md"
    csv_path = md_path.with_suffix(".csv")
    tex_path = md_path.with_suffix(".tex")

    df = pd.DataFrame(rows, columns=["Statistic", "Value"])
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    md = ("# Table 1. Descriptive statistics — linked medical-device "
          "warning-letter sample\n\n"
          + df.to_markdown(index=False) + "\n\n*Notes:* " + notes + "\n")
    md_path.write_text(md, encoding="utf-8")

    body = "\n".join(f"{s} & {v} \\\\" for s, v in rows)
    tex = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage[hang,flushmargin]{footmisc}
\pagestyle{empty}
\begin{document}
\begin{table}[h!]
\centering
\caption{Descriptive statistics --- linked medical-device warning-letter sample}
\begin{tabular}{lr}
\toprule
 & \multicolumn{1}{c}{Value} \\
\midrule
""" + body.replace("$M", r"\$M").replace("%", r"\%").replace("–", "--") + r"""
\bottomrule
\end{tabular}

\vspace{1em}
\begin{minipage}{0.92\textwidth}
\footnotesize
\emph{Notes:} """ + (notes.replace("$", r"\$").replace("%", r"\%")
                     .replace("–", "--")) + r"""
\end{minipage}
\end{table}
\end{document}
"""
    tex_path.write_text(tex, encoding="utf-8")

    # Compile the PDF with pdflatex (MiKTeX). Run in output/tables; clean aux.
    res = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", tex_path.name],
        cwd=TABLES_DIR, capture_output=True, text=True)
    pdf_path = tex_path.with_suffix(".pdf")
    if res.returncode != 0 or not pdf_path.exists():
        print("    WARNING: pdflatex failed — PDF not produced. "
              "Tail of log:\n" + res.stdout[-1500:])
    for ext in (".aux", ".log", ".out"):
        p = tex_path.with_suffix(ext)
        if p.exists():
            p.unlink()
    return [csv_path, md_path, tex_path] + ([pdf_path] if pdf_path.exists() else [])


# =============================================================
# STEP 4. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    sub = build_subdataset()
    funda, uni, live = fetch_wrds(sub)
    sub = attach_fundamentals(sub, funda)

    # Active-at-letter-date filter (see header): require pre-letter market
    # cap. This is what makes the sample usable for capital-market tests.
    n_before, f_before = len(sub), sub["gvkey"].nunique()
    sub = sub[sub["mktcap_preletter"].notna()].copy()
    print(f"    active-at-letter-date filter: {n_before} -> {len(sub)} "
          f"letter-firm rows; {f_before} -> {sub['gvkey'].nunique()} firms")

    data_path = PROCESSED_DIR / f"device_letters_linked_{snapshot_date}.csv"
    sub.to_csv(data_path, index=False, encoding="utf-8-sig")
    print(f"    sub-dataset saved -> {data_path.relative_to(REPO_ROOT)}")

    share, n_in, n_uni = universe_share(sub, uni, live)
    rows, nmc, nta, n_in, n_uni = build_rows(sub, share, n_in, n_uni)
    ta_gap = ("" if nta == nmc else
              f" (total assets available for {nta} of the {nmc} firms)")
    notes = NOTES.format(ta_gap=ta_gap, nin=n_in, nuni=n_uni)

    print("[3/4] Writing table (md / csv / tex / pdf) ...")
    written = write_outputs(rows, notes, snapshot_date)

    print("[4/4] Written:")
    for p in written:
        print(f"  {p.relative_to(REPO_ROOT)}")
    print()
    print(pd.DataFrame(rows, columns=["Statistic", "Value"])
          .to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
