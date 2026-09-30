# FDA Data Dashboard: device inspections by fiscal year

`fda_dashboard_device_inspections_by_fy_2026-09-27.csv` - pulled 2026-09-27 from the FDA Data
Dashboard, Inspections page (https://datadashboard.fda.gov/oii/cd/inspections.htm), by querying the
page's own Qlik data engine (the same data behind "Download Dataset -> Entire Dataset") from the
browser. Public US government data. FY = federal fiscal year (Oct 1 - Sep 30). FY2026 is partial.

Column definitions (Qlik set-analysis expressions, grouped by [Fiscal Year]):

| Column | Expression |
|---|---|
| device_inspections | `Count({<[Product Type]={'Devices'}>} distinct [Inspection ID])` |
| oai_final | same, plus `Classification={'Official Action Indicated (OAI)'}` - inspections with any device OAI (FINAL classification) |
| vai_not_oai | device inspections with a VAI classification and no OAI classification |
| inspections_with_483_citations | `Count({<[Program Area]={'Devices'}>} distinct [Inspection ID])` (citations dataset: inspections with >=1 device Form 483 citation) |
| device_483_citations | `Count({<[Program Area]={'Devices'}>} [Act/CFR Number])` |
| compliance_inspections | device inspections in Project Area 'Compliance: Devices' (the quality-system compliance inspections FDA's annual Quality System Data reports count) |
| compliance_oai_final | same, with a FINAL classification of OAI |
| qs_21cfr820_citations | same, restricted to `[Act/CFR Number]={"21 CFR 820*"}` (quality-system rule citations) |

Notes: one inspection can carry several classifications (several project areas); counts use
distinct inspection IDs. The dashboard shows FINAL classifications; FDA's annual CDRH
"Medical Device Quality System Data" reports (CY2014-FY2017) show INITIAL classifications.
Citations data cover inspections documented in FDA's electronic inspection system.
