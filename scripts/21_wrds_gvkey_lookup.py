# =============================================================
# Script: 21_wrds_gvkey_lookup.py
# Author: Armando Cuello (built with Claude Code)
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: Look up Compustat gvkeys (WRDS comp.company) for the publicly traded
#          warning-letter companies that are not yet in the project's Compustat
#          files, by SEC CIK - with a company-name search as a fallback for any
#          CIK Compustat does not carry (common for foreign ADR issuers).
# Inputs:  WRDS login (you are prompted; nothing is stored in this script)
# Outputs: data/raw/compustat_gvkey_lookup_<YYYY-MM-DD>.csv       CIK matches - script 19 uses these
#                                                                  automatically on its next run
#          data/raw/compustat_gvkey_name_search_<YYYY-MM-DD>.csv  name-search candidates for CIKs
#                                                                  Compustat lacks - review by hand;
#                                                                  NOT used automatically
#          (both gitignored; WRDS terms)
# Run:     python scripts/21_wrds_gvkey_lookup.py
# =============================================================
from datetime import date
from pathlib import Path

import pandas as pd
import wrds

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# SEC CIK -> name, for the 17 companies marked "look up in WRDS" in the
# "All letters with gvkey" tab of warning_letters_summary_by_year_<date>.xlsx
MISSING = {
    1067983: "BERKSHIRE HATHAWAY", 19446: "CANTEL MEDICAL", 711404: "COOPER COMPANIES",
    313616: "DANAHER", 866374: "FLEX", 40545: "GENERAL ELECTRIC", 711665: "PHOTOMEDEX",
    895655: "JARDEN", 831967: "KINETIC CONCEPTS", 313216: "PHILIPS", 1607962: "REWALK",
    1373060: "MINDRAY", 1039065: "OSI SYSTEMS", 31791: "PERKINELMER", 882835: "ROPER",
    1160110: "VEOLIA", 1555280: "ZOETIS",
}


def main():
    db = wrds.Connection()                       # prompts for your WRDS username and password
    try:
        ciks = ",".join(f"'{c:010d}'" for c in MISSING)
        by_cik = db.raw_sql(f"select gvkey, conm, cik, tic, fic, costat from comp.company where cik in ({ciks})")
        found = {int(c) for c in by_cik.cik.dropna()}
        cands = []
        for cik, name in MISSING.items():         # fallback: name search for CIKs Compustat lacks
            if cik not in found:
                hit = db.raw_sql(f"select gvkey, conm, cik as compustat_cik, tic, fic, costat from comp.company "
                                 f"where upper(conm) like '%%{name}%%'")
                hit.insert(0, "sec_cik_searched_for", cik)
                hit.insert(1, "name_searched", name)
                cands.append(hit)
    finally:
        db.close()

    today = date.today().isoformat()
    path = RAW_DIR / f"compustat_gvkey_lookup_{today}.csv"
    by_cik.to_csv(path, index=False)
    print(by_cik.to_string(index=False))
    print(f"\n{len(by_cik)} companies matched by CIK -> {path}")
    if cands:
        cpath = RAW_DIR / f"compustat_gvkey_name_search_{today}.csv"
        pd.concat(cands, ignore_index=True).to_csv(cpath, index=False)
        print(f"Not found by CIK: {', '.join(MISSING[c] for c in MISSING if c not in found)}")
        print(f"Name-search candidates (check by hand) -> {cpath}")


if __name__ == "__main__":
    main()
