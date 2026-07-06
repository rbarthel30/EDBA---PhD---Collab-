# =============================================================
# Script: 05_backfill_subsidiary_gvkey_links.py
# Author: Ryan Barthel
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Recover gvkey links for warning-letter recipients that script 04's
#          conservative exact match could NOT link — chiefly SUBSIDIARIES and
#          foreign affiliates of public firms (e.g., "Fresenius Kabi Oncology
#          Ltd." is a Fresenius Kabi unit; "Janssen Pharmaceutica N.V." is
#          Johnson & Johnson). Three tiers, in decreasing trust order:
#
#          Tier A — CURATED subsidiary->gvkey mappings imported from Ryan's
#                   Clinical Trial Disclosure project (hand-checked overrides
#                   with ownership-change windows, a resolved sponsor
#                   crosswalk, and a device-sponsor list). Auto-accepted.
#          Tier B — PARENT-PREFIX matches: the FDA name begins with a
#                   distinctive Compustat company name and extends it
#                   (subsidiary-style). Auto-accepted but ALWAYS flagged
#                   review_suggested=True.
#          Tier C — FUZZY candidates (rapidfuzz similarity >= 90). NEVER
#                   auto-accepted: written to a review worklist where a human
#                   marks accept/reject. Precision over recall, as always.
#
# Inputs:  data/processed/compliance_actions_gvkey_crosswalk_<date>.csv (script 04)
#          data/processed/compliance_actions_unmatched_<date>.csv       (script 04)
#          data/raw/compustat_company_<date>.csv                        (script 04's WRDS pull)
#          data/external/ct_sponsor_overrides_supplemental.csv          (CT project, hand-curated)
#          data/external/ct_sponsor_to_gvkey_crosswalk_extended_20260505.csv (CT project)
#          data/external/ct_dropped_device_sponsors.csv                 (CT project, device firms)
# Outputs: data/processed/compliance_actions_gvkey_crosswalk_full_<date>.csv
#             (script-04 matches + Tier A + Tier B, with provenance and
#              ownership-window columns)
#          data/processed/compliance_actions_fuzzy_candidates_<date>.csv
#             (Tier C worklist for manual accept/reject)
#          data/processed/compliance_actions_unmatched_remaining_<date>.csv
#             (medtech/pharma names still unlinked after Tiers A + B)
#
# Companion doc: data/compliance_actions_gvkey_crosswalk_replication_instructions.md (Section 5)
#
# OWNERSHIP WINDOWS: some curated mappings are time-varying (Wyeth is itself
# pre-2009 and Pfizer after; Genzyme is itself pre-2011 and Sanofi after).
# The crosswalk therefore carries valid_from_year / valid_to_year columns and
# such names can appear on MULTIPLE rows. Downstream joins must respect the
# window: join on name AND require valid_from_year <= letter year <= valid_to_year.
# =============================================================

# -------------------------------------------------------------
# 0. Imports and configuration
# -------------------------------------------------------------
import glob
import re
import sys
from datetime import date
from pathlib import Path
from collections import defaultdict

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
EXTERNAL_DIR = REPO_ROOT / "data" / "external"

# Tier C: similarity floor for the manual-review worklist. 90 keeps the list
# short and high-yield; lower it to cast a wider (noisier) net.
FUZZY_CUTOFF = 90

# Tier B guards: a Compustat name only qualifies as a "parent prefix" if it is
# distinctive enough that a coincidental prefix is implausible.
PREFIX_MIN_CHARS = 8    # normalized parent name must be at least this long ...
PREFIX_MIN_TOKENS = 2   # ... and have at least this many words


# =============================================================
# STEP 1. Company-name normalization (identical to scripts 02/04)
# =============================================================
# Kept in sync BY HAND across scripts 02/04/05 — if you edit one, edit all.

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


def latest(pattern: str) -> Path:
    """Most recent date-stamped file matching a glob pattern."""
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching {pattern} — run the "
                                "upstream script first.")
    return Path(files[-1])


# =============================================================
# STEP 2. Tier A — curated mapping table from the Clinical Trial project
# =============================================================
def build_curated_map(company: pd.DataFrame) -> pd.DataFrame:
    """
    Combine the three Clinical-Trial-project files into one candidate table:
    normalized_key -> (gvkey, valid_from_year, valid_to_year, source, note).
    Where the same key appears in several sources, the most trusted source
    wins:  ct_override > ct_resolved > ct_dropped_device > ct_fuzzy.
    """
    frames = []

    # --- 2a. Hand-curated overrides, WITH ownership windows. gvkey='UNMAPPED'
    # is meaningful: a known subsidiary whose parent is not in Compustat
    # North America (e.g., Genentech under Roche) — resolved, not matchable.
    ov = pd.read_csv(EXTERNAL_DIR / "ct_sponsor_overrides_supplemental.csv",
                     dtype={"gvkey": str})
    frames.append(pd.DataFrame({
        "key": ov["lead_sponsor_name"].map(normalize_name),
        "gvkey": ov["gvkey"],
        "valid_from_year": ov["start_year"],
        "valid_to_year": ov["end_year"],
        "source": "ct_override_windowed",
        "note": ov["note"],
    }))

    # --- 2b. Extended sponsor crosswalk. Its own tiers become ours; fuzzy
    # rows carry their original similarity score in the note.
    cx = pd.read_csv(EXTERNAL_DIR /
                     "ct_sponsor_to_gvkey_crosswalk_extended_20260505.csv",
                     dtype={"gvkey": str})
    # Note: the extended crosswalk's own "override" rows are WHOLE-PERIOD
    # (no ownership windows) — trusted, but below the windowed supplemental.
    src_rank = {"override": "ct_override", "resolved": "ct_resolved",
                "fuzzy_extended": "ct_fuzzy"}
    frames.append(pd.DataFrame({
        "key": cx["sponsor_norm"].map(normalize_name),
        "gvkey": cx["gvkey"],
        "valid_from_year": 1900,
        "valid_to_year": 2099,
        "source": cx["map_source"].map(src_rank).fillna("ct_fuzzy"),
        "note": ("CT crosswalk (" + cx["map_source"].astype(str)
                 + cx["map_score"].map(lambda s: f", score {s:.0f}"
                                       if pd.notna(s) else "") + ")"),
    }))

    # --- 2c. Device sponsors the CT project dropped as "non-pharma" — for us
    # they are in-scope. They carry a Compustat company NAME (orig_conm), not
    # a gvkey, so recover the gvkey by exact conm lookup in the master.
    dr = pd.read_csv(EXTERNAL_DIR / "ct_dropped_device_sponsors.csv")
    gvkey_by_conm = (company.drop_duplicates("conm", keep=False)
                     .set_index("conm")["gvkey"])
    dr["gvkey"] = dr["orig_conm"].map(gvkey_by_conm)
    dr = dr.dropna(subset=["gvkey"])
    frames.append(pd.DataFrame({
        "key": dr["lead_sponsor_name"].map(normalize_name),
        "gvkey": dr["gvkey"],
        "valid_from_year": 1900,
        "valid_to_year": 2099,
        "source": "ct_dropped_device",
        "note": "CT device-sponsor list (conm: " + dr["orig_conm"] + ")",
    }))

    cand = pd.concat(frames, ignore_index=True)
    cand = cand[cand["key"] != ""]

    # --- 2d. Resolve duplicates: keep the most trusted source per
    # (key, window). Distinct windows for one key are legitimate (Wyeth).
    trust = {"ct_override_windowed": 0, "ct_override": 1, "ct_resolved": 2,
             "ct_dropped_device": 3, "ct_fuzzy": 4}
    cand["trust"] = cand["source"].map(trust)
    cand = (cand.sort_values("trust")
                .drop_duplicates(["key", "valid_from_year", "valid_to_year"],
                                 keep="first"))

    # Where a key has hand-curated WINDOWED override rows, they supersede all
    # other sources for that key — otherwise a whole-period row (e.g.
    # "allergan" -> AbbVie for 1900-2099 in the extended crosswalk) would
    # falsely conflict with the windowed ownership history (Allergan plc
    # through 2019, AbbVie from 2020).
    windowed_keys = set(cand.loc[cand["source"] == "ct_override_windowed",
                                 "key"])
    cand = cand[(cand["source"] == "ct_override_windowed")
                | ~cand["key"].isin(windowed_keys)]

    # --- 2e. Precision guard: a key whose surviving rows disagree on gvkey
    # over OVERLAPPING windows is internally inconsistent -> drop entirely.
    def windows_conflict(g):
        rows = g[["gvkey", "valid_from_year", "valid_to_year"]].values
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                (gi, fi, ti), (gj, fj, tj) = rows[i], rows[j]
                if gi != gj and fi <= tj and fj <= ti:   # overlap, diff gvkey
                    return True
        return False

    bad_keys = [k for k, g in cand.groupby("key") if windows_conflict(g)]
    if bad_keys:
        print(f"    dropped {len(bad_keys)} internally inconsistent curated "
              f"keys (conflicting gvkeys): {bad_keys[:5]} ...")
        cand = cand[~cand["key"].isin(bad_keys)]

    return cand.drop(columns="trust")


# =============================================================
# STEP 3. Tier B — parent-prefix subsidiary matching
# =============================================================
def build_prefix_index(company: pd.DataFrame):
    """
    Index of distinctive normalized Compustat names (from conm AND conml)
    usable as parent prefixes. Names shared by >1 gvkey are excluded.
    """
    key_gvkeys = defaultdict(set)
    for _, row in company.iterrows():
        for name in (row["conm"], row["conml"]):
            k = normalize_name(name)
            if (len(k) >= PREFIX_MIN_CHARS
                    and len(k.split()) >= PREFIX_MIN_TOKENS):
                key_gvkeys[k].add(row["gvkey"])
    return {k: next(iter(g)) for k, g in key_gvkeys.items() if len(g) == 1}


def prefix_match(fda_key: str, prefix_index: dict):
    """
    Return (gvkey, parent_key) if the FDA name starts with a distinctive
    Compustat name at a word boundary and EXTENDS it (strictly longer), else
    (None, None). Longest qualifying parent wins.
    """
    tokens = fda_key.split()
    # Try prefixes from longest to shortest, minus the full name itself
    # (the full name was already tried by script 04's exact match).
    for n in range(len(tokens) - 1, 1, -1):
        candidate = " ".join(tokens[:n])
        if len(candidate) < PREFIX_MIN_CHARS:
            break
        if candidate in prefix_index:
            return prefix_index[candidate], candidate
    return None, None


# =============================================================
# STEP 4. Tier C — fuzzy candidates for manual review
# =============================================================
def fuzzy_candidates(unmatched: pd.DataFrame, company: pd.DataFrame) -> pd.DataFrame:
    """
    For every still-unmatched medtech/pharma name, find the single most
    similar Compustat name with similarity >= FUZZY_CUTOFF. Output is a
    WORKLIST — nothing here enters the crosswalk until a human fills the
    'accept' column and the accepted rows are folded in (documented in the
    replication doc).
    """
    from rapidfuzz import fuzz, process

    # Candidate universe: unique normalized Compustat names -> unique gvkey.
    key_gvkeys = defaultdict(set)
    for _, row in company.iterrows():
        for name in (row["conm"], row["conml"]):
            k = normalize_name(name)
            if k:
                key_gvkeys[k].add(row["gvkey"])
    uniq = {k: next(iter(g)) for k, g in key_gvkeys.items() if len(g) == 1}
    choices = list(uniq.keys())

    rows = []
    for _, r in unmatched.iterrows():
        best = process.extractOne(r["normalized_name"], choices,
                                  scorer=fuzz.token_sort_ratio,
                                  score_cutoff=FUZZY_CUTOFF)
        if best is None:
            continue
        comp_key, score, _ = best
        rows.append({
            "company_name_fda": r["company_name_fda"],
            "normalized_name": r["normalized_name"],
            "candidate_compustat_name": comp_key,
            "candidate_gvkey": uniq[comp_key],
            "similarity": round(score, 1),
            "n_letters": r["n_letters"],
            "product_types": r["product_types"],
            "accept": "",   # <- human fills TRUE / FALSE
        })
    return (pd.DataFrame(rows)
            .sort_values("similarity", ascending=False, ignore_index=True))


# =============================================================
# STEP 5. Orchestrate
# =============================================================
def main() -> None:
    snapshot_date = date.today().isoformat()

    print("=" * 60)
    print("Back-fill subsidiary gvkey links (Tiers A/B/C)")
    print(f"Snapshot date: {snapshot_date}")
    print("=" * 60)

    # --- 5a. Load script-04 outputs and the Compustat master. ---
    cw_path = latest(str(PROCESSED_DIR / "compliance_actions_gvkey_crosswalk_2*.csv"))
    # "2*" pins the date-stamped script-04 file and excludes this script's
    # own "..._unmatched_remaining_" output on re-runs.
    um_path = latest(str(PROCESSED_DIR / "compliance_actions_unmatched_2*.csv"))
    comp_path = latest(str(RAW_DIR / "compustat_company_*.csv"))
    matched04 = pd.read_csv(cw_path, dtype={"gvkey": str})
    unmatched = pd.read_csv(um_path, dtype={"gvkey": str})
    company = pd.read_csv(comp_path, dtype={"gvkey": str})
    print(f"[1/5] Loaded {len(matched04):,} script-04 matches, "
          f"{len(unmatched):,} unmatched medtech/pharma names, "
          f"{len(company):,} Compustat firms")

    # Drop script-04's empty match columns — each tier below re-derives them,
    # and keeping them would collide in merges.
    unmatched = unmatched.drop(
        columns=["match_status", "gvkey", "company_name_compustat",
                 "n_gvkey_candidates", "review_suggested"]).copy()
    unmatched["key"] = unmatched["company_name_fda"].map(normalize_name)

    # --- 5b. Tier A: curated CT-project mappings (windows respected). ---
    print("[2/5] Tier A: curated subsidiary mappings (CT project) ...")
    curated = build_curated_map(company)

    # OWNERSHIP CORRECTION for script-04 exact matches: an exact name match
    # can still point at a stale owner (letters to "Genentech, Inc." after
    # 2009 belong to Roche, not to the pre-buyout GENENTECH INC gvkey).
    # Wherever the hand-curated WINDOWED overrides cover an exact-matched
    # name, the windowed mapping replaces the exact match.
    windowed_keys = set(curated.loc[curated["source"] == "ct_override_windowed",
                                    "key"])
    needs_corr = matched04["normalized_name"].isin(windowed_keys)
    corrected = pd.DataFrame()
    if needs_corr.any():
        corr_names = matched04.loc[needs_corr, "company_name_fda"].tolist()
        print(f"    ownership-window correction replaces {len(corr_names)} "
              f"exact matches: {corr_names[:5]}"
              f"{' ...' if len(corr_names) > 5 else ''}")
        corrected = (matched04.loc[needs_corr,
                     ["company_name_fda", "normalized_name", "n_letters",
                      "first_letter_date", "last_letter_date",
                      "any_device_letter", "any_drug_letter",
                      "any_biologic_letter", "any_medtech_pharma",
                      "product_types"]]
                     .rename(columns={"normalized_name": "key"}))
        matched04 = matched04[~needs_corr]

    tierA = unmatched.merge(curated, on="key", how="inner")
    if len(corrected):
        tierA = pd.concat([tierA, corrected.merge(curated, on="key")],
                          ignore_index=True)
    # 'UNMAPPED' = known subsidiary of a firm outside Compustat NA: resolved
    # (drop from the manual worklist) but carries no gvkey.
    tierA_unlisted = tierA[tierA["gvkey"] == "UNMAPPED"].copy()
    tierA = tierA[tierA["gvkey"] != "UNMAPPED"]
    print(f"    matched {tierA['company_name_fda'].nunique():,} names "
          f"({int(tierA.drop_duplicates('company_name_fda').n_letters.sum()):,} letters); "
          f"{tierA_unlisted['company_name_fda'].nunique():,} resolved as "
          "subsidiaries of unlisted parents")

    resolved_names = set(tierA["company_name_fda"]) | set(tierA_unlisted["company_name_fda"])
    remaining = unmatched[~unmatched["company_name_fda"].isin(resolved_names)].copy()

    # --- 5c. Tier B: parent-prefix subsidiary matches. ---
    print("[3/5] Tier B: parent-prefix matching ...")
    prefix_index = build_prefix_index(company)
    conm_by_gvkey = dict(zip(company["gvkey"], company["conm"]))
    hits = remaining["key"].map(lambda k: prefix_match(k, prefix_index))
    remaining["gvkey"] = hits.map(lambda t: t[0])
    remaining["parent_key"] = hits.map(lambda t: t[1])
    tierB = remaining[remaining["gvkey"].notna()].copy()
    remaining = remaining[remaining["gvkey"].isna()].drop(
        columns=["gvkey", "parent_key"])
    print(f"    matched {len(tierB):,} names "
          f"({int(tierB.n_letters.sum()):,} letters) — all flagged for review")

    # --- 5d. Assemble the combined crosswalk with provenance. ---
    print("[4/5] Writing combined crosswalk ...")
    matched04 = matched04.assign(match_source="exact_normalized",
                                 valid_from_year=1900, valid_to_year=2099,
                                 match_note="")

    def as_crosswalk(df, source, review, note_col=None, comp_name=None):
        out = pd.DataFrame({
            "company_name_fda": df["company_name_fda"],
            "normalized_name": df["key"],
            "match_status": "matched",
            "gvkey": df["gvkey"],
            "company_name_compustat": (df["gvkey"].map(conm_by_gvkey)
                                       if comp_name is None else comp_name),
            "n_gvkey_candidates": 1,
            "review_suggested": review,
            "n_letters": df["n_letters"],
            "first_letter_date": df["first_letter_date"],
            "last_letter_date": df["last_letter_date"],
            "any_device_letter": df["any_device_letter"],
            "any_drug_letter": df["any_drug_letter"],
            "any_biologic_letter": df["any_biologic_letter"],
            "any_medtech_pharma": df["any_medtech_pharma"],
            "product_types": df["product_types"],
            "match_source": source,
            "valid_from_year": df.get("valid_from_year", 1900),
            "valid_to_year": df.get("valid_to_year", 2099),
            "match_note": df[note_col] if note_col else "",
        })
        return out

    tierA_rows = as_crosswalk(tierA, tierA["source"], False, note_col="note")
    tierB_rows = as_crosswalk(tierB, "parent_prefix", True)
    tierB_rows["match_note"] = "parent prefix: " + tierB["parent_key"].values

    unlisted_rows = as_crosswalk(tierA_unlisted, tierA_unlisted["source"],
                                 False, note_col="note",
                                 comp_name=pd.NA)
    unlisted_rows["match_status"] = "resolved_unlisted_parent"
    unlisted_rows["gvkey"] = pd.NA

    full = pd.concat([matched04, tierA_rows, tierB_rows, unlisted_rows],
                     ignore_index=True)
    full_path = (PROCESSED_DIR /
                 f"compliance_actions_gvkey_crosswalk_full_{snapshot_date}.csv")
    full.sort_values(["company_name_fda", "valid_from_year"]).to_csv(
        full_path, index=False, encoding="utf-8-sig")

    remaining_path = (PROCESSED_DIR /
                      f"compliance_actions_unmatched_remaining_{snapshot_date}.csv")
    remaining.drop(columns=["key"]).to_csv(
        remaining_path, index=False, encoding="utf-8-sig")

    # --- 5e. Tier C: fuzzy worklist from what is still unmatched. ---
    print("[5/5] Tier C: fuzzy candidates (manual review worklist) ...")
    fuzzy = fuzzy_candidates(remaining, company)
    fuzzy_path = (PROCESSED_DIR /
                  f"compliance_actions_fuzzy_candidates_{snapshot_date}.csv")
    fuzzy.to_csv(fuzzy_path, index=False, encoding="utf-8-sig")

    # --- Summary. ---
    mp = full[(full["match_status"] == "matched") & full["any_medtech_pharma"]]
    uniq_firms = mp["gvkey"].nunique()
    print()
    print("Summary (medtech/pharma, matched rows)")
    print(f"  exact (script 04)         : "
          f"{(mp['match_source'] == 'exact_normalized').sum():,} names")
    for s in ["ct_override_windowed", "ct_override", "ct_resolved",
              "ct_dropped_device", "ct_fuzzy"]:
        n = (mp["match_source"] == s).sum()
        if n:
            print(f"  {s:<26}: {n:,} names")
    print(f"  parent_prefix (review!)   : "
          f"{(mp['match_source'] == 'parent_prefix').sum():,} names")
    print(f"  unique gvkeys             : {uniq_firms:,}")
    print(f"  letters covered           : "
          f"{int(mp.drop_duplicates('company_name_fda').n_letters.sum()):,}")
    print(f"  resolved, unlisted parent : "
          f"{(full['match_status'] == 'resolved_unlisted_parent').sum():,} names")
    print(f"  still unmatched           : {len(remaining):,} names "
          f"(fuzzy worklist: {len(fuzzy):,} candidates)")
    print(f"  crosswalk -> {full_path.relative_to(REPO_ROOT)}")
    print(f"  remaining -> {remaining_path.relative_to(REPO_ROOT)}")
    print(f"  fuzzy     -> {fuzzy_path.relative_to(REPO_ROOT)}")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI script
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
