# Table 1. FDA Warning Letters — descriptive counts by year

| Year   |   Warning letters |   Device letters |   Drug letters |   Biologic letters |   Letters linked to gvkey |   Unique gvkey firms |
|:-------|------------------:|-----------------:|---------------:|-------------------:|--------------------------:|---------------------:|
| 2008   |                98 |               30 |             18 |                  5 |                         4 |                    4 |
| 2009   |               561 |              164 |            152 |                 21 |                        29 |                   26 |
| 2010   |               619 |              179 |            146 |                  9 |                        43 |                   41 |
| 2011   |               751 |              199 |            109 |                 11 |                        37 |                   33 |
| 2012   |               737 |              216 |             76 |                 21 |                        29 |                   26 |
| 2013   |               634 |              186 |             87 |                 16 |                        24 |                   23 |
| 2014   |               631 |              157 |             97 |                  7 |                        24 |                   23 |
| 2015   |               576 |              157 |             89 |                  4 |                        25 |                   25 |
| 2016   |               516 |               62 |            171 |                  4 |                        12 |                   11 |
| 2017   |               460 |               44 |            169 |                  5 |                        10 |                    8 |
| 2018   |               299 |               33 |            123 |                  8 |                        11 |                   11 |
| 2019   |               361 |               36 |            161 |                 11 |                        10 |                   10 |
| 2020   |               483 |               47 |            222 |                 15 |                         7 |                    7 |
| 2021   |               386 |               61 |            142 |                  5 |                         9 |                    9 |
| 2022   |               421 |               26 |            163 |                 11 |                         7 |                    6 |
| 2023   |               369 |               31 |            165 |                 10 |                        15 |                   13 |
| 2024   |               415 |               42 |            173 |                 23 |                        15 |                   15 |
| 2025   |               471 |               58 |            283 |                 21 |                        19 |                   16 |
| 2026   |               297 |               23 |            166 |                 13 |                         9 |                    8 |
| Total  |              9085 |             1751 |           2712 |                220 |                       339 |                  238 |

Notes:
- Source: FDA Data Dashboard compliance actions (scripts 03-05), snapshot 2026-07-06. Tobacco-retailer letters are excluded upstream by script 03.
- Letters are counted by unique Case/Injunction ID. A letter spanning several product types (e.g., Devices and Drugs) counts once in 'Warning letters' but appears in each product column, so product columns need not sum to the total.
- 'Letters linked to gvkey' / 'Unique gvkey firms' are restricted to the analysis universe (device, drug, or biologic letters). They count links INCLUSIVE of matches flagged for manual review (review_suggested = True in the crosswalk), and respect ownership windows (a letter links only to the firm that owned the recipient in the letter year).
- 2008 and 2026 are partial years (coverage starts 2008-10-01; snapshot taken 2026-07-06).
