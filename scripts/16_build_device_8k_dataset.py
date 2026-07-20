# =============================================================
# Script: 16_build_device_8k_dataset.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Filter the classified 8-K set (script 15) down to MEDICAL-DEVICE
#          event disclosures - the outcome dataset for the paper - and record
#          WHY each filing qualifies so the rule stays auditable.
#
# ---------------------------------------------------------------------------
# THE INCLUSION RULE, AND WHY IT IS NOT JUST `is_device_domain`
#
#   The obvious filter - keep rows whose text scores as device domain - is
#   WRONG, and measurably so. 148 of 356 flagged filings score 'unspecified':
#   the filing never names a product class, because it does not need to. A
#   typical warning-letter 8-K reads "the Company received a Warning Letter
#   from the FDA relating to its Elyria, Ohio facility" and stops there.
#
#   71 of those 'unspecified' filings are at DEVICE-SIC firms, and inspection
#   shows they are unambiguous device events: Stryker recalls, Invacare
#   warning letters, Merit Medical, Animas insulin pumps. A text-only filter
#   discards every one of them - roughly a third of the real device sample.
#
#   The reverse error is just as real: 17 filings at PHARMA/BIO-SIC firms
#   carry clear device-domain text. That is the Abbott/J&J pattern - the
#   largest device makers are classified in pharma SIC codes - so an
#   SIC-only filter would drop genuine device events too.
#
#   Neither signal alone is sufficient. The rule therefore uses text evidence
#   where it exists and falls back to industry where the text is silent:
#
#     INCLUDE  product_domain == 'device'                  (any SIC)
#     INCLUDE  product_domain in ('unspecified','mixed')   AND device SIC
#     EXCLUDE  product_domain in ('drug','biologic')       (any SIC)
#     EXCLUDE  product_domain in ('unspecified','mixed')   AND pharma/bio SIC
#
#   Every kept row carries `device_evidence` = 'text' or 'sic_fallback', so a
#   stricter text-only sample is one filter away and the fallback's weight can
#   be reported rather than hidden.
# ---------------------------------------------------------------------------
#
# NOTE ON EXCLUDED AMBIGUITY: 'unspecified' at a pharma/bio firm is dropped
#   because the prior runs the other way - a drug maker's warning letter is
#   most likely about a drug. Those rows are NOT deleted; they remain in
#   8k_all_classified_<DATE>.csv with their flags, so the decision is
#   reversible and inspectable.
#
# Inputs:  data/processed/8k_event_disclosures_<DATE>.csv   (script 15)
# Outputs: data/processed/8k_device_event_disclosures_<DATE>.csv
#          output/tables/8k_device_descriptives_<DATE>.md
#
# Usage:   python scripts/16_build_device_8k_dataset.py
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import sys
import glob
from datetime import date
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
TABLES_DIR = REPO_ROOT / "output" / "tables"

DEVICE_SIC = (3841, 3845)
PHARMA_BIO_SIC = (2833, 2836)
PANEL_EVENTS = ["warning_letter", "adverse_event", "recall"]


def latest(directory: Path, pattern: str) -> Path:
    """Return the most recent date-stamped file matching a glob pattern."""
    hits = sorted(glob.glob(str(directory / pattern)))
    if not hits:
        raise FileNotFoundError(f"No file matches {pattern} in {directory}")
    return Path(hits[-1])


def sic_bucket(sic) -> str:
    """Classify an EDGAR SIC into the two in-scope industry buckets."""
    try:
        s = int(float(sic))
    except (TypeError, ValueError):
        return "unknown"
    if DEVICE_SIC[0] <= s <= DEVICE_SIC[1]:
        return "device"
    if PHARMA_BIO_SIC[0] <= s <= PHARMA_BIO_SIC[1]:
        return "pharma_bio"
    return "unknown"


# =============================================================
# STEP 1. Apply the inclusion rule
# =============================================================
def build_device_set(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the two-signal rule and label each row's evidence source."""
    # Restrict to filings that are about one of the three PANEL events.
    # Untitled letters are excluded here: they are a different regulatory
    # artefact with no counterpart in the treatment panel (see script 15).
    out = df[df["n_flags"] > 0].copy()
    out["sic_bucket"] = out["sic"].map(sic_bucket)

    is_device_text = out["product_domain"].eq("device")
    is_silent = out["product_domain"].isin(["unspecified", "mixed"])
    is_device_sic = out["sic_bucket"].eq("device")

    keep = is_device_text | (is_silent & is_device_sic)
    out["device_evidence"] = pd.NA
    out.loc[is_device_text, "device_evidence"] = "text"
    out.loc[is_silent & is_device_sic & ~is_device_text,
            "device_evidence"] = "sic_fallback"

    kept = out[keep].copy()
    print(f"    flagged panel-event filings : {len(out):,}")
    print(f"    kept as medical-device      : {len(kept):,} "
          f"({len(kept) / max(len(out), 1):.1%})")
    print(f"       via device text          : "
          f"{int((kept['device_evidence'] == 'text').sum()):,}")
    print(f"       via SIC fallback         : "
          f"{int((kept['device_evidence'] == 'sic_fallback').sum()):,}")
    dropped = out[~keep]
    print(f"    dropped                     : {len(dropped):,}")
    for dom, n in dropped["product_domain"].value_counts().items():
        print(f"       {dom:<14} {n:,}")
    return kept


# =============================================================
# STEP 2. Descriptives
# =============================================================
def describe(d: pd.DataFrame, snapshot_date: str) -> str:
    """Build the descriptive block written to output/tables/."""
    lines = []
    add = lines.append
    yrs = pd.to_datetime(d["file_date"], errors="coerce").dt.year

    add(f"# Medical-device 8-K event disclosures ({snapshot_date})\n")
    add("| Statistic | Value |")
    add("|:---|---:|")
    add(f"| Device event disclosures (8-K filings) | {len(d):,} |")
    add(f"| Distinct filers (CIK) | {d['cik'].nunique():,} |")
    add(f"| File-date range | {int(yrs.min())}-{int(yrs.max())} |")
    add(f"| Identified by device text | "
        f"{int((d['device_evidence'] == 'text').sum()):,} |")
    add(f"| Identified by SIC fallback | "
        f"{int((d['device_evidence'] == 'sic_fallback').sum()):,} |\n")

    add("## By event type\n")
    add("| Event type | Filings | Filers | Via text | Via SIC fallback |")
    add("|:---|---:|---:|---:|---:|")
    for ev in PANEL_EVENTS:
        s = d[d[f"flag_{ev}"]]
        if s.empty:
            add(f"| {ev} | 0 | 0 | 0 | 0 |")
            continue
        add(f"| {ev} | {len(s):,} | {s['cik'].nunique():,} | "
            f"{int((s['device_evidence'] == 'text').sum()):,} | "
            f"{int((s['device_evidence'] == 'sic_fallback').sum()):,} |")
    add("")

    add("## By document type\n")
    add("| Lead source | Filings |")
    add("|:---|---:|")
    for k, n in d["lead_source"].value_counts().items():
        label = ("8-K form (Item-anchored)" if k == "item_anchored"
                 else "Exhibit / press release (top)")
        add(f"| {label} | {n:,} |")
    add("")

    add("## Filings per year\n")
    add("| Year | Filings |")
    add("|:---|---:|")
    for y, n in yrs.value_counts().sort_index().items():
        add(f"| {int(y)} | {n:,} |")
    add("")

    add("*Inclusion rule:* a filing is medical-device if its text scores as "
        "device domain (any SIC), or its text is silent on product class "
        "('unspecified'/'mixed') AND the filer is device-SIC 3841-3845. Drug "
        "and biologic filings are excluded regardless of SIC, as are "
        "text-silent filings at pharma/bio filers. `device_evidence` records "
        "which signal qualified each row.")
    add("")
    add("> **Caveats.** (1) Classification uses the filing's LEAD - the text "
        "after each `Item X.XX` heading, or the top of the document for "
        "exhibits/press releases - never the full body; body matching would "
        "have produced ~6,300 false positives on warning letters alone. "
        "(2) EDGAR full-text search indexes 2001+ only, and the modern 8-K "
        "item structure dates from August 2004, so earlier disclosures are "
        "absent by construction. (3) Adverse-event (MDR) disclosures are "
        "genuinely rare - firms seldom file an 8-K about an individual "
        "Medical Device Report - so that count is small for substantive, not "
        "technical, reasons.")
    return "\n".join(lines)


# =============================================================
# STEP 3. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("Medical-device 8-K event disclosures")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 64)

    # Match the date stamp explicitly rather than a bare wildcard: a suffixed
    # sibling (e.g. '..._2026-07-19_SUPERSEDED.csv') sorts AFTER the real file
    # and would silently be picked as "latest".
    src = latest(PROCESSED_DIR, "8k_event_disclosures_[0-9][0-9][0-9][0-9]-"
                                "[0-9][0-9]-[0-9][0-9].csv")
    print(f"[1/3] Reading {src.name} ...")
    df = pd.read_csv(src, low_memory=False)

    print("[2/3] Applying the medical-device inclusion rule ...")
    device = build_device_set(df)

    out_path = PROCESSED_DIR / f"8k_device_event_disclosures_{snapshot_date}.csv"
    device.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"    dataset -> {out_path.relative_to(REPO_ROOT)}")

    print("[3/3] Descriptives ...")
    md = describe(device, snapshot_date)
    md_path = TABLES_DIR / f"8k_device_descriptives_{snapshot_date}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"    descriptives -> {md_path.relative_to(REPO_ROOT)}\n")
    sys.stdout.reconfigure(errors="replace")
    print(md)
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
