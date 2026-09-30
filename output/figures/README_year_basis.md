# Year basis of the warning-letter charts (read before comparing numbers)

The same 1,760 FDA device warning letters (distinct FDA case numbers, Oct 2, 2008 - Sep 1, 2026)
are grouped by **different year definitions** in different outputs, so single-year counts differ
while the totals match.

| Output | Year basis | Example: 2016 |
|---|---|---|
| `data/processed/warning_letters_summary_by_year_<date>.xlsx` (and charts made from it, e.g. the bar chart shared with the dissertation chair, Sept 2026) | **Calendar year** (Jan-Dec) | 62 |
| `output/figures/device_inspections_vs_warning_letters.*` and `..._table.xlsx` (script 22) | **Federal fiscal year** (Oct 1 - Sep 30; FY2016 = Oct 2015 - Sep 2016) | 81 |

Why fiscal years in script 22: FDA's inspection data (Data Dashboard) is recorded by fiscal year,
so letters are grouped the same way to compare them with inspections.

Partial years: calendar 2008 covers Oct-Dec only (the FDA file starts Oct 2, 2008); 2026 runs only to
Sep 1, 2026 (calendar 2026 = Jan-Sep 1; FY2026 = Oct 2025 - Sep 1, 2026).

| Year | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Calendar year | 30 | 164 | 179 | 199 | 216 | 186 | 157 | 157 | 62 | 44 | 33 | 36 | 47 | 61 | 26 | 31 | 42 | 59 | 31 | 1,760 |
| Fiscal year | - | 136 | 197 | 179 | 216 | 218 | 147 | 167 | 81 | 44 | 35 | 32 | 52 | 57 | 25 | 32 | 42 | 49 | 51 | 1,760 |

Decision (2026-09-27): keep both as they are for now; if the dissertation uses one basis
throughout, fiscal years are recommended for anything compared with inspection data.
