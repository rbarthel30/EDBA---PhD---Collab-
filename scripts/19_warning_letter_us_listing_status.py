# =============================================================
# Script: 19_warning_letter_us_listing_status.py
# Author: Armando Cuello (built with Claude Code)
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: For every FDA device warning letter in the Data Dashboard export,
#          decide whether the recipient was PUBLICLY TRADED ON A US EXCHANGE
#          (NYSE, Nasdaq, NYSE American/MKT, Cboe) ON THE DATE THE LETTER WAS
#          ISSUED. A subsidiary of a US-listed parent is flagged with the
#          PARENT's ticker (status "Yes - via parent").
# Inputs:  data/raw/Copy_FDA Warning Letter_Data.xlsx   (sheet "Extracted Data from FDA Website")
#          SEC EDGAR submissions JSON (cached in data/raw/edgar_submissions_cache/)
#          data/processed/fda_firm_gvkey_crosswalk_unified_2026-07-19.csv  (cik -> gvkey, optional)
#          data/processed/gvkey_year_event_panel_2026-07-19.csv            (cik -> gvkey, optional)
#          SEC EDGAR company list for the device SIC codes (cached in data/raw/edgar_device_sic_ciks.json)
# Outputs: data/processed/warning_letters_us_listing_status_<YYYY-MM-DD>.xlsx
#          (incl. sheet "Sample vs industry by year": sample firms vs all
#           US-listed medical-device companies, device SIC codes, per year)
#          data/processed/warning_letters_summary_by_year_<YYYY-MM-DD>.xlsx
#          ("Summary by year" + "How the data was pulled")
#
# HOW A RECIPIENT IS LINKED (hand curation, see CURATION below)
#   All 1,632 distinct recipient names were reviewed by hand. A name is linked
#   to an SEC issuer only when it IS that issuer or is a known subsidiary /
#   division of it. Ownership changes are dated (acquisition / spin-off closing
#   dates), so the SAME name can be "Yes" in one year and "No" in another
#   (e.g., Beckman Coulter: itself until 2011-06-30, then Danaher). Automatic
#   exact-name matches against EDGAR and the project's gvkey crosswalks were
#   used only as leads: many were false positives (e.g. "Best Vascular" ->
#   BEST Inc.) and were rejected. Names not linked default to "No" (private,
#   individual, hospital/IRB, or foreign firm without a US exchange listing).
#
# HOW "LISTED ON THE LETTER DATE" IS TESTED (SEC EDGAR filing history)
#   The linked issuer must be
#     (a) a REPORTING company at the letter date: a 10-K/10-Q/20-F/40-F filed
#         within ~15 months before the letter (or a fresh IPO registration),
#         and no Form 15 deregistration in between; and
#     (b) EXCHANGE-listed, not OTC: an exchange registration (Form 8-A12B /
#         10-12B) on or before the letter date with no later exchange
#         delisting (Form 25 followed by a 12(g) registration or Form 15), OR
#         currently listed on a US exchange with continuous reporting (listings
#         older than EDGAR's 8-A records).
#   Reporting companies that trade only OTC are "No". Cases the filing record
#   cannot settle are "Unclear" and listed on the "Needs review" sheet.
#
# NOTE: SEC's fair-access policy requires a contact in the User-Agent; set
#       SEC_USER_AGENT to override the project default (as scripts 15/17).
# =============================================================
import json, os, re, time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
CACHE_DIR = RAW_DIR / "edgar_submissions_cache"
INPUT_XLSX = RAW_DIR / "Copy_FDA Warning Letter_Data.xlsx"
INPUT_SHEET = "Extracted Data from FDA Website"

SEC_UA = {"User-Agent": os.environ.get(
    "SEC_USER_AGENT", "University of Miami Research rbarthel15@gmail.com")}


# =============================================================
# STEP 1. CURATION: recipient name -> SEC issuer, by dated period
# =============================================================
# Hand-curated links: letter recipient name -> the SEC issuer whose US listing is tested.
# Each entry: list of periods (start, end, cik, relation, parent_label, confidence, note)
# relation: "self" = the recipient itself is the issuer; "parent" = public parent's ticker.
# Dates are acquisition/spin closing dates; the recipient's status on the letter date
# follows whichever period contains it. Outside all periods -> "No" with the note given in NOTE_NO.
LO, HI = "1900-01-01", "2100-01-01"
JNJ, ABT, PHG, NVS, COV, BAX, DHR, COO = 200406, 1800, 313216, 1114448, 1385187, 10456, 313616, 711404
MDT_INC, MDT_PLC, ZBH, BDX, SYK, IART = 64670, 1613103, 1136869, 10795, 310764, 917520
def S(cik, conf="high", note="", a=LO, b=HI): return (a, b, cik, "self", "", conf, note)
def P(cik, label, conf="high", note="", a=LO, b=HI): return (a, b, cik, "parent", label, conf, note)
C = {
 "3M Company": [S(66740)],
 "AMO Uppsala AB": [P(1168335, "Advanced Medical Optics", b="2009-02-26"), P(ABT, "Abbott Laboratories", a="2009-02-26", note="Abbott acquired Advanced Medical Optics 2009-02-26")],
 "Abaxis Inc": [S(881890, b="2018-07-31"), P(1555280, "Zoetis", a="2018-07-31", note="Zoetis acquired Abaxis 2018-07-31")],
 "Abbott Diabetes Care, Inc.": [P(ABT, "Abbott Laboratories")],
 "Abbott Medical": [P(ABT, "Abbott Laboratories")],
 "Abbott Molecular, Inc.": [P(ABT, "Abbott Laboratories")],
 "Abbott Point of Care Canada Limited": [P(ABT, "Abbott Laboratories")],
 "Abiomed, Inc.": [S(815094, b="2022-12-22"), P(JNJ, "Johnson & Johnson", a="2022-12-22", note="J&J acquired Abiomed 2022-12-22")],
 "Acclarent, Inc.": [P(JNJ, "Johnson & Johnson", note="J&J (Ethicon) owned Acclarent 2010-2022")],
 "Advanced Sterilization Products": [P(JNJ, "Johnson & Johnson", b="2019-04-01", note="J&J owned ASP until sale to Fortive 2019")],
 "Agena Bioscience, Inc.": [P(724004, "Mesa Laboratories", a="2022-10-20", note="Mesa Labs acquired Agena 2022-10")],
 "Agilent Technologies Denmark ApS": [P(1090872, "Agilent Technologies")],
 "Alcon LenSx, Inc.": [P(NVS, "Novartis AG (ADR)", a="2011-04-08", b="2019-04-09", note="Alcon was a Novartis division 2011-2019")],
 "Alere San Diego, Inc.": [P(1145460, "Alere Inc", b="2017-10-03")],
 "Align Technology Inc": [S(1097149)],
 "Allergan Sales, LLC": [P(1578845, "Allergan plc", b="2020-05-08"), P(1551152, "AbbVie", a="2020-05-08", note="AbbVie acquired Allergan 2020-05-08")],
 "Alphatec Spine, Inc.": [P(1350653, "Alphatec Holdings")],
 "AngioDynamics, Inc.": [S(1275187)], "Angiodynamics Inc": [S(1275187)], "Angiodynamics, Inc.": [S(1275187)],
 "Animas Corporation": [P(JNJ, "Johnson & Johnson", note="J&J acquired Animas 2006")],
 "Argo Medical Technologies Inc.": [P(1607962, "ReWalk Robotics (now Lifeward)", note="Argo Medical Technologies is ReWalk's operating predecessor/subsidiary")],
 "Artivion, Inc": [S(784199, note="named CryoLife, Inc. at the time")],
 "Atossa Genetics, Inc.": [S(1488039)],
 "Avanos Medical, Inc.": [P(55785, "Kimberly-Clark", b="2014-10-31", note="FDA shows the current name; the business was Kimberly-Clark Health Care until the Halyard spin-off 2014-10-31"), S(1606498, a="2014-10-31")],
 "Bard Peripheral Vascular Inc": [P(9892, "C. R. Bard", b="2017-12-29")],
 "Bausch Health Americas, Inc.": [P(885590, "Valeant Pharmaceuticals (now Bausch Health)")],
 "Baxter Healthcare Corporation": [P(BAX, "Baxter International")],
 "Baxter Healthcare Renal Div": [P(BAX, "Baxter International")],
 "Beckman Coulter Inc.": [S(840467, b="2011-06-30"), P(DHR, "Danaher", a="2011-06-30", note="Danaher acquired Beckman Coulter 2011-06-30")],
 "Beckman Coulter, Inc.": [S(840467, b="2011-06-30"), P(DHR, "Danaher", a="2011-06-30", note="Danaher acquired Beckman Coulter 2011-06-30")],
 "Becton Dickinson & Company": [S(BDX)], "Becton Dickinson Medical Systems": [P(BDX, "Becton Dickinson")],
 "Beta Bionics, Inc.": [S(1674632)],
 "Bio-Rad Laboratories GmbH": [P(12208, "Bio-Rad Laboratories")],
 "BioElectronics Corporation": [S(1320869)],
 "Biomet, Inc.": [P(ZBH, "Zimmer Biomet", a="2015-06-24", note="Biomet was privately held (LBO) before the Zimmer merger 2015-06-24; its pre-merger SEC filings were for debt only")],
 "Blackstone Medical Inc.": [P(884624, "Orthofix")],
 "Boston Scientific Corporation": [S(885725)],
 "C. R. Bard, Inc.": [S(9892)], "C.R. Bard Inc.": [S(9892)],
 "CIBA Vision Puerto Rico, Inc.": [P(NVS, "Novartis AG (ADR)")],
 "CUE HEALTH INC": [S(1628945)],
 "Canon Medical Components U.S.A., Inc.": [P(16988, "Canon Inc (ADR)")],
 "Cardinal Health 200, LLC": [P(721371, "Cardinal Health")],
 "CareFusion 303, Inc.": [P(1457543, "CareFusion", b="2015-03-17"), P(BDX, "Becton Dickinson", a="2015-03-17", note="BD acquired CareFusion 2015-03-17")],
 "Carefusion 2200 Inc": [P(1457543, "CareFusion", b="2015-03-17"), P(BDX, "Becton Dickinson", a="2015-03-17")],
 "Cellestis Inc": [P(1015820, "Qiagen N.V.", a="2011-08-01")],
 "Cepheid Ab": [P(1037760, "Cepheid", b="2016-11-04"), P(DHR, "Danaher", a="2016-11-04")],
 "Childrens Medical Ventures": [P(PHG, "Koninklijke Philips (ADR)", note="Respironics subsidiary; Philips acquired Respironics 2008")],
 "Church & Dwight Inc": [S(313927)],
 "Coastal Contacts Inc.": [S(1322232)],
 "ConMed Corporation": [S(816956)],
 "Conformis Inc.": [S(1305773)],
 "CooperSurgical, Inc.": [P(COO, "The Cooper Companies")], "CooperVision, Inc.": [P(COO, "The Cooper Companies")],
 "CooperVisision Manufacturing Puerto Rico LLC": [P(COO, "The Cooper Companies")],
 "Cordis LLC": [P(JNJ, "Johnson & Johnson", b="2015-10-19", note="J&J sold Cordis to Cardinal Health 2015-10")],
 "Covidien, LP": [P(COV, "Covidien plc", b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "Cutera, Inc.": [S(1162461)],
 "DNA Genotek Inc.": [P(1116463, "OraSure Technologies", a="2011-08-01")],
 "DePuy Orthopaedics, Inc.": [P(JNJ, "Johnson & Johnson")],
 "Dentsply Sirona Inc.": [S(818479)],
 "Dexcom, Inc.": [S(1093557)],
 "EMD Millipore Corporation": [P(66479, "Millipore Corp", b="2010-07-14", note="FDA shows the current name; Millipore was independent and NYSE-listed until Merck KGaA acquired it 2010-07-14")],
 "Edwards Lifesciences, LLC": [P(1099800, "Edwards Lifesciences")],
 "Entellus Medical Inc.": [S(1374128, b="2018-02-01")],
 "Envoy Medical Corporation": [S(1840877)],
 "Flextronics America LLC": [P(866374, "Flex Ltd")],
 "Flextronics Electronics Technology (Suzhou) Co., Ltd.": [P(866374, "Flex Ltd")],
 "Flir System AB": [P(354908, "FLIR Systems", b="2021-05-14")],
 "Fresenius Medical Care Renal Therapies Group, LLC": [P(1333141, "Fresenius Medical Care (ADR)")],
 "Fresenius USA Manufacturing, Inc.": [P(1333141, "Fresenius Medical Care (ADR)")],
 "Globus Medical, Inc.": [S(1237831)],
 "Haemoscope Division of Haemonetics Corp": [P(313143, "Haemonetics")],
 "Heartware, Inc.": [S(1389072, b="2016-08-23")],
 "Hill-Rom Inc": [P(47518, "Hill-Rom Holdings", b="2021-12-13")],
 "Hologic, Inc": [S(859737)],
 "Hooper Holmes, Inc.": [S(741815)],
 "Hospira Inc": [S(1274057)], "Hospira, Inc.": [S(1274057)],
 "ICU Medical Costa Rica Ltd.": [P(883984, "ICU Medical")], "ICU Medical Inc.": [S(883984)], "ICU Medical, Inc.": [S(883984)],
 "Insulet Corporation": [S(1145197)],
 "Integra LifeSciences Corp. (NeuroSciences)": [P(IART, "Integra LifeSciences Holdings")],
 "Integra LifeSciences Corporation": [P(IART, "Integra LifeSciences Holdings")],
 "Integra NeuroSciences Ltd.": [P(IART, "Integra LifeSciences Holdings")],
 "Integra Neurosciences": [P(IART, "Integra LifeSciences Holdings")],
 "Intuitive Surgical, Inc.": [S(1035267)],
 "Invacare Corporation": [S(742112)],
 "Invatec S.p.A.": [P(MDT_INC, "Medtronic, Inc.", a="2010-04-01", b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "IsoTis OrthoBiologics, Inc.": [P(884624, "Orthofix Medical", "medium", a="2023-01-05", note="IsoTis passed Integra -> SeaSpine (2015) -> Orthofix (SeaSpine merger 2023-01-05)")],
 "Isomedix Operations, Inc.": [P(815065, "STERIS Corp", b="2015-11-02")],
 "Kenvue Brands LLC": [P(JNJ, "Johnson & Johnson", b="2023-05-04", note="FDA shows the current name; the business was J&J's consumer unit until the Kenvue IPO 2023-05")],
 "Kerr Corporation": [P(DHR, "Danaher", note="Sybron Dental/Kerr owned by Danaher 2006-2019")],
 "Kimberly-Clark Corporation": [S(55785)],
 "LCA Vision Inc": [S(1003130)], "LCA Vision Inc.": [S(1003130)], "LCA Vision, Inc": [S(1003130)],
 "LCA Vision Inc/Lasik Plus Vision Center": [S(1003130)],
 "Lasik Plus": [P(1003130, "LCA-Vision", "medium", note="LasikPlus was LCA-Vision's center brand")],
 "Lasik Plus Houston": [P(1003130, "LCA-Vision", "medium", note="LasikPlus was LCA-Vision's center brand")],
 "Lasik Plus Vision Center": [P(1003130, "LCA-Vision", "medium", note="LasikPlus was LCA-Vision's center brand")],
 "LasikPlus": [P(1003130, "LCA-Vision", "medium", note="LasikPlus was LCA-Vision's center brand")],
 "LasikPlus Vision Center": [P(1003130, "LCA-Vision", "medium", note="LasikPlus was LCA-Vision's center brand")],
 "Labcorp- PMD": [P(920148, "Laboratory Corp of America")],
 "LeMaitre Vascular, Inc.": [S(1158895)],
 "Leica Microsystems NC Inc.": [P(DHR, "Danaher")],
 "LifeCell Corporation": [S(849448, b="2008-05-27"), P(831967, "Kinetic Concepts (KCI)", a="2008-05-27", b="2011-11-04", note="KCI acquired LifeCell 2008-05-27; KCI taken private by Apax 2011-11-04")],
 "LivaNova Deutschland GmbH": [P(1639691, "LivaNova PLC", a="2015-10-19", note="Before 2015-10-19 this was Sorin Group, listed only in Milan")],
 "LivaNova USA Inc.": [P(1639691, "LivaNova PLC", a="2015-10-19", note="Before 2015-10-19 this was Sorin/Cyberonics; Cyberonics was Nasdaq-listed")],
 "Luminex Corporation": [S(1033905, b="2021-07-14")],
 "Magellan Diagnostics, Inc.": [P(794172, "Meridian Bioscience", a="2016-03-23", b="2023-01-31", note="Meridian owned Magellan from 2016-03; Meridian taken private 2023-01-31")],
 "Masimo Corporation": [S(937556)],
 "Measurement Specialties, Inc.": [S(778734)],
 "MedLine Industries, LP (NAMIC Division)": [P(2046386, "Medline Inc.", "medium", note="Medline Inc. IPO on Nasdaq 2025-12")],
 "Medline Industries, LP": [P(2046386, "Medline Inc.", "medium", note="Medline was privately held until its 2025-12 IPO")],
 "Medivators Inc": [P(19446, "Cantel Medical")],
 "Medtronic MiniMed, Inc.": [P(MDT_INC, "Medtronic, Inc.", b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "Medtronic Navigation, Inc.": [P(MDT_INC, "Medtronic, Inc.", b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "Medtronic Neuromodulation": [P(MDT_INC, "Medtronic, Inc.", b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "Medtronic Puerto Rico Operations Co.": [P(MDT_INC, "Medtronic, Inc.", b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "Medtronic, Inc.": [S(MDT_INC, b="2015-01-26"), P(MDT_PLC, "Medtronic plc", a="2015-01-26")],
 "Mentor Worldwide LLC": [P(JNJ, "Johnson & Johnson", note="J&J acquired Mentor 2009")],
 "Merge Healthcare, Inc.": [S(944765, b="2015-10-13"), P(51143, "IBM", a="2015-10-13")],
 "Merit Medical Ireland Ltd.": [P(856982, "Merit Medical Systems")],
 "Mindray DS USA, Inc.": [P(1373060, "Mindray Medical International (ADR)", b="2016-03-01")],
 "Moog Inc": [S(67887)],
 "NCS Pearson": [P(938323, "Pearson plc (ADR)")],
 "Natus Europe GmbH": [P(878526, "Natus Medical", b="2022-07-21")], "Natus Medical Incorporated": [S(878526, b="2022-07-21")],
 "Nephros, Inc.": [S(1196298)],
 "Non-Invasive Monitoring Systems, Inc.": [S(720762)],
 "Northern Digital Inc.": [P(882835, "Roper Industries", "medium", note="Roper acquired Northern Digital 2011")],
 "NuVasive Inc": [S(1142596)],
 "OWLET BABY CARE INC": [P(1816708, "Owlet, Inc.", a="2021-07-15", note="Owlet listed via SPAC merger 2021-07-15")],
 "Ocular Therapeutix Inc.": [S(1393434)],
 "Orthosoft, Inc.": [P(ZBH, "Zimmer Holdings / Zimmer Biomet")],
 "Outset Medical, Inc.": [S(1484612)],
 "Oxysure Systems, Inc.": [S(1413797)],
 "Penumbra Inc.": [S(1321732)],
 "Philips Healthcare": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips Healthcare (Suzhou) Co., Ltd.": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips Medical Systems (Cleveland) Inc": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips Medical Systems Nederland B.V.": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips North  America, LLC": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips North America LLC": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips Respironics, Inc.": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips Ultrasound, Inc": [P(PHG, "Koninklijke Philips (ADR)")],
 "Philips Ultrasound, LLC": [P(PHG, "Koninklijke Philips (ADR)")],
 "PhotoMedex, Inc.": [S(711665)],
 "Power Medical Interventions, Inc": [S(1398090)],
 "Prodesse, Inc": [P(820237, "Gen-Probe", "medium", a="2009-10-01", note="Gen-Probe acquired Prodesse 2009-10")],
 "Qiagen Sciences LLC": [P(1015820, "Qiagen N.V.")],
 "Repro-Med Systems, Inc.": [S(704440)],
 "Revvity Health Sciences Inc": [P(31791, "PerkinElmer (now Revvity)")],
 "Sanmina-SCI AB": [P(897723, "Sanmina")],
 "Scottcare Corporation": [P(1067983, "Berkshire Hathaway", "medium", note="ScottCare is a Scott Fetzer company; Scott Fetzer is owned by Berkshire Hathaway")],
 "Western/Scott Fetzer Company": [P(1067983, "Berkshire Hathaway", note="Scott Fetzer owned by Berkshire Hathaway since 1986")],
 "Siemens Healthcare Diagnostics, Inc.": [P(1135644, "Siemens AG (ADR)")],
 "Sientra, Inc": [S(1551693)],
 "Sintx Technologies Inc": [S(1269026, note="then named Amedica Corp")],
 "Smith & Nephew Inc.": [P(845982, "Smith & Nephew plc (ADR)")],
 "Smith & Nephew Orthopaedics GmbH": [P(845982, "Smith & Nephew plc (ADR)")],
 "Smith & Nephew, Inc.": [P(845982, "Smith & Nephew plc (ADR)")],
 "Solta Medical Inc": [S(1171298)],
 "Spacelabs Healthcare, Inc.": [P(1039065, "OSI Systems")],
 "Spectranetics Corporation": [S(789132)],
 "St. Jude Medical": [S(203077)],
 "Staar Surgical Company": [S(718937)],
 "Sterilmed Inc.": [P(JNJ, "Johnson & Johnson", "medium", a="2011-11-01", note="J&J (Ethicon Endo-Surgery) acquired SterilMed 2011")],
 "Steris Corporation": [S(815065)],
 "STOCKERT GMBH": [P(JNJ, "Johnson & Johnson", "medium", note="Stockert GmbH (EP generators) is a Biosense Webster / J&J company")],
 "Stryker Corporation": [S(SYK)], "Stryker Craniomaxillofacial Division": [P(SYK, "Stryker")],
 "Stryker Medical London dba CHG Hospital Beds": [P(SYK, "Stryker", "medium")],
 "Summer Infant, Inc.": [S(1314772)],
 "Sunbeam Products, Inc.": [P(895655, "Jarden Corp")],
 "Symmetry Medical USA, Inc": [P(1292055, "Symmetry Medical")],
 "Symmetry Surgical, Inc.": [P(1292055, "Symmetry Medical", b="2014-12-05", note="FDA shows the current name; the unit was Symmetry Medical's until the 2014-12 spin-off")],
 "Syneron, Inc.": [P(1291361, "Syneron Medical")],
 "Synthes, Inc.": [P(JNJ, "Johnson & Johnson", a="2012-06-14", note="Before 2012-06-14 Synthes was listed only on SIX Swiss Exchange")],
 "TEI Biosciences, Inc.": [P(IART, "Integra LifeSciences Holdings", "medium", a="2015-07-01", note="Integra acquired TEI Biosciences 2015")],
 "TLC Laser Eye Center": [P(1010610, "TLC Vision")],
 "TLC Laser Eye Center d/b/a/ TLC Pittsburgh": [P(1010610, "TLC Vision")],
 "TLC Laser Eye Centers": [P(1010610, "TLC Vision")],
 "TLC Vision Corporation": [S(1010610)],
 "Tlc Eye Care - Lansing": [P(1010610, "TLC Vision", "medium")],
 "TYRX Inc.": [P(MDT_PLC, "Medtronic plc", a="2015-01-26"), P(MDT_INC, "Medtronic, Inc.", a="2014-01-01", b="2015-01-26")],
 "Thoratec LLC": [P(350907, "Thoratec Corp", b="2015-10-08")],
 "Tyco Healthcare Canada": [P(COV, "Covidien plc")],
 "UV Flu Technologies Inc.": [S(1385310)],
 "Valeant Amsterdam Logistics Center": [P(885590, "Valeant Pharmaceuticals")],
 "Varian Medical Systems, Inc.": [S(203527)],
 "Veolia Water Treatment & Solutions": [P(1160110, "Veolia Environnement (ADR)", "medium")],
 "Vital Signs Devices, a GE Healthcare Company": [S(865846, b="2008-10-06"), P(40545, "General Electric", "medium", a="2008-10-06", note="GE acquired Vital Signs 2008-10")],
 "Vivos Therapeutics, Inc.": [S(1716166)],
 "XTANT Medical Holdings, Inc": [S(1453593, note="then named Bacterin International Holdings")],
 "ZOLL Medical Corporation": [S(887568, b="2012-04-26")], "Zoll Medical Corporation": [S(887568, b="2012-04-26")],
 "Zevex, Inc.": [P(67887, "Moog Inc")],
 "Zhejiang Biomet Medical Products Co. Ltd.": [P(ZBH, "Zimmer Biomet", a="2015-06-24")],
 "Zimmer Manufacturing B.V.": [P(ZBH, "Zimmer Holdings / Zimmer Biomet")],
 "iRhythm Technologies, Inc.": [S(1388658)],
 "Arrayit Corporation": [S(1084507)],
 "Kelyniam Global, Inc.": [S(1372114)],
 "ZYTO Technologies, Inc.": [S(1406796)],
}
# Recipients linked to a parent that is NOT listed on a US exchange (or otherwise explained 'No').
NOTE_NO = {
 "AGFA Healthcare Corp.": "Agfa-Gevaert: listed on Euronext Brussels only", "AGFA Healthcare Corporation": "Agfa-Gevaert: listed on Euronext Brussels only",
 "Aizu Olympus Co., Ltd.": "Olympus: Tokyo listing; US ADR trades OTC only", "OLYMPUS MEDICAL SYSTEMS CORP. Hinode Plant": "Olympus: Tokyo listing; US ADR OTC only",
 "OLYMPUS TERUMO BIOMATERIALS CORP. MISHIMA FACTORY": "Olympus/Terumo: Tokyo listings only", "Olympus Corporation of the Americas": "Olympus: Tokyo listing; US ADR OTC only",
 "Olympus Medical Systems Corporation": "Olympus: Tokyo listing; US ADR OTC only", "Gyrus Medical Ltd.": "Olympus subsidiary; Olympus US ADR OTC only",
 "Aesculap AG": "B. Braun subsidiary (privately held)", "Laboratorios B. Braun S.A.": "B. Braun (privately held)",
 "Ambu Inc.": "Ambu A/S: Copenhagen listing only", "King Systems Corp.": "Private in 2009; Ambu A/S (Copenhagen) from 2010",
 "Arjo Inc.": "Getinge/Arjo: Stockholm listing only", "Arjo Med. AB": "Getinge/Arjo: Stockholm listing only",
 "Atrium Medical Corporation": "Getinge (Maquet) subsidiary: Stockholm listing only", "Datascope Corp.": "Getinge (Maquet) subsidiary since 2009: Stockholm listing only",
 "Maquet Cardiopulmonary Gmbh": "Getinge: Stockholm listing only", "Maquet Cardiovascular, LLC": "Getinge: Stockholm listing only",
 "Bayer Medical Care, Inc.": "Bayer AG: Frankfurt listing; US ADR OTC only", "Biocompatibles Inc.": "BTG plc: London listing only",
 "Biomerieux Inc": "bioMérieux: Euronext Paris only", "bioMerieux, Inc.": "bioMérieux: Euronext Paris only",
 "Biotronik SE & Co. KG": "Privately held", "Boule Medical AB": "Boule Diagnostics: Stockholm only",
 "Criticare Systems (Malaysia) Sdn. Bhd.": "Opto Circuits (India) subsidiary since 2008", "Criticare Technologies, Inc.": "Privately held",
 "ConvaTec, Inc": "Privately held (Nordic Capital/Avista) at letter date", "Unomedical Device S.A. de C.V.": "ConvaTec Group: London listing only", "Unomedical s.r.o.": "ConvaTec: private/London only",
 "Cook Incorporated": "Privately held (Cook Group)", "Cook Vandergrift, Inc.": "Privately held (Cook Group)", "Wilson-Cook Medical Inc.": "Privately held (Cook Group)",
 "Draeger Medical Systems, Inc.": "Drägerwerk: Frankfurt listing only", "Dornier Medtech America, Inc.": "Privately held", "Dornier Medtech GmbH": "Privately held",
 "Eiken Chemical Co., Ltd. NOGI PLANT": "Tokyo listing only", "EIKEN CHEMICAL CO., LTD. NOGI PLANT": "Tokyo listing only",
 "Ellex iScience, Inc.": "Nova Eye Medical: ASX listing only", "Evoqua Water Technologies LLC": "Privately held (AEA) before 2017 IPO",
 "Exactech Sarasota, Inc.": "Privately held (TPG) since 2018", "Exactech, Inc.": "Privately held (TPG) since 2018",
 "FUJIFILM Healthcare Americas Corporation": "Fujifilm: Tokyo listing; US ADR OTC only", "Fujifilm Corporation": "Tokyo listing; US ADR OTC only",
 "Fresenius Hemocare Deutschland GmbH": "Fresenius SE/Kabi: Frankfurt only", "Fresenius Hemocare Netherlands B.V": "Fresenius SE/Kabi: Frankfurt only",
 "Fresenius Kabi USA LLC (FK USA)": "Fresenius SE/Kabi: Frankfurt only", "Fresenius Kabi USA, LLC": "Fresenius SE/Kabi: Frankfurt only", "Fresenius SE & Co. KGaA": "Frankfurt listing; US ADR OTC only",
 "Gambro Dasco SPA Monitors Division": "Gambro privately held in 2009", "Gambro Dialysatoren GmbH": "Gambro privately held in 2009", "Gambro Renal Products S.A. de C.V.": "Gambro privately held in 2009",
 "Gentherm Medical, LLC": "FDA shows current name; the firm was privately held Cincinnati Sub-Zero until Gentherm bought it in 2019",
 "HOYA Corporation PENTAX Miyagi Factory": "Hoya: Tokyo only", "Hoya Corporation - Pentax Life Division": "Hoya: Tokyo only", "Hoya Surgical Optics, Inc.": "Hoya: Tokyo only", "Pentax of America Inc": "Hoya: Tokyo only",
 "Karl Storz Endovision, Inc.": "Privately held", "Karl Storz GMBH & Co KG   (KSVEM)": "Privately held", "STORZ ENDOSKOP PRODUKTIONS GMBH": "Privately held (Karl Storz)",
 "Key Surgical LLC": "Privately held in 2015 (STERIS bought it 2019)", "Lifewatch Services Inc": "LifeWatch AG: SIX Swiss only", "Linde Gas & Equiment Inc.": "Linde AG: Frankfurt only in 2015",
 "Lonza Walkersville, Inc.": "Lonza: SIX Swiss only", 
 "MicroPort CRM S.r.l.": "Sorin Group (Milan) in 2009", "MicroPort Orthopedics Inc.": "MicroPort: Hong Kong only", "MicroVention Costa Rica S.R.L.": "Terumo: Tokyo only",
 "Sorin CRM SAS": "Sorin Group: Milan only", "NIDEK Co., Ltd.": "Privately held", "Nidek Medical Products Inc": "Privately held", "Nidek, Inc.": "Privately held",
 "NIPRO CANADA CORPORATION": "Nipro: Tokyo only", "Nipro Renal Solutions USA, Corporation": "Nipro: Tokyo only",
 "Nihon Kohden Digital Health Solutions, LLC.": "Nihon Kohden: Tokyo only", "Nikkiso Medical America, Inc": "Nikkiso: Tokyo only",
 "Oridion Medical 1987 Ltd.": "Oridion Systems: SIX Swiss only in 2011", "Ortho Clinical Diagnostics Gmbh": "Privately held (Carlyle) in 2015",
 "Terumo BCT, Inc.": "Terumo: Tokyo only", "Terumo Medical Corporation": "Terumo: Tokyo only", "Terumo Medical Products (Hangzhou) Co., Ltd.": "Terumo: Tokyo only",
 "ThyssenKrupp Access Corp": "ThyssenKrupp AG: Frankfurt; US ADR OTC", "ThyssenKrupp Access Manufacturing, LLC": "ThyssenKrupp AG: Frankfurt; US ADR OTC",
 "Topcon Corporation": "Tokyo only", "Tosoh Bioscience Inc": "Tosoh: Tokyo only", "USHIO GERMANY GmbH": "Ushio: Tokyo only",
 "Zoll Manufacturing Corp.": "Asahi Kasei (Tokyo) subsidiary since 2012", "Asahi Kasei Medical MT Corp.  Oita Works": "Asahi Kasei: Tokyo only",
 "Horiba Instruments Incorporated": "Horiba: Tokyo only", "Sekisui Medical Co., Ltd": "Sekisui Chemical: Tokyo only",
 "Guangdong Biolight Meditech Co., Ltd": "Shenzhen listing only", "GUANGDONG BIOLIGHT MEDITECH CO., LTD": "Shenzhen listing only", "Lepu Medical Technology (Beijing) Co., Ltd.": "Shenzhen listing only",
 "Polymer Technology Systems, Inc.": "Sinocare (Shenzhen) subsidiary from 2019", "GVS Filter Technology UK, Ltd.": "GVS: Milan only",
 "Quanta System SpA": "El.En.: Milan only", "Quanta Aesthetic Lasers USA, LLC": "El.En.: Milan only",
 "Interacoustics A/S": "Demant: Copenhagen only", "Crothall Healthcare Inc": "Compass Group: London; US ADR OTC",
 "Perma Pure LLC": "Halma plc: London only", "Compumedics Germany Gmbh": "Compumedics: ASX only", "Marel Corporation": "Marel: Iceland/Amsterdam only",
 "Stille AB": "Stockholm only", "Advanced Vision Science Inc": "Santen: Tokyo only", "Alma Lasers, Inc.": "Privately held (TA Associates / Fosun)",
 "Aptalis Pharma Us Inc": "Privately held (TPG); SEC filings were for debt only", "Pyng Medical Corporation": "TSX Venture listing only",
 "Medivance Instruments Ltd.": "UK private firm", "VWR Chemicals, Llc": "Privately held in 2013 (VWR IPO 2014-10)", "Excelsior Medical LLC": "Privately held",
 "Heartsine Technologies Inc": "Privately held (Stryker bought it 2016)", "Stanmore Implants Worldwide Ltd.": "Privately held (Stryker bought it 2016)",
 "Centurion Medical Products, LP": "Medline subsidiary; Medline privately held in 2020", "JAS Diagnostics, Inc./Drew Scientific, Inc.": "ERBA group; not US-exchange listed in 2022",
  "Ferrosan Medical Devices A/s": "Privately held in 2015", "Penn Pharmaceutical Services Limited": "Privately held",
 "ORTHOPEDIATRICS CANADA ULC": "OrthoPediatrics was private until its 2017 IPO", "Pioneer Surgical Technology Inc.": "Privately held (RTI bought it 2013)",
  
}
UNCLEAR_NAMES = {
    "Sterilmed Inc.": "Letter 2011-10-26 falls close to J&J's 2011 acquisition of SterilMed; closing date not confirmed",
    "TEI Biosciences, Inc.": "Integra acquired TEI Biosciences in 2015; whether it closed before the 2015-05-29 letter is not confirmed (later letters are via Integra)",
    "Lone Star Medical Products, Inc.": "Possibly a CooperSurgical (Cooper Companies) unit; ownership at the 2013 letter date not confirmed",
}

# Ticker and exchange AT THE LETTER DATE where they differ from (or are missing
# in) SEC's current record — defunct, renamed, or exchange-switching issuers.
TICKER_AT = {
    1168335: "EYE", 881890: "ABAX", 815094: "ABMD", 1145460: "ALR", 1578845: "AGN", 784199: "CRY",
    9892: "BCR", 840467: "BEC", 1457543: "CFN", 1037760: "CPHD", 1385187: "COV", 1374128: "ENTL",
    354908: "FLIR", 1389072: "HTWR", 47518: "HRC", 741815: "HH", 1274057: "HSP", 895655: "JAH",
    831967: "KCI", 1003130: "LCAV", 849448: "LIFC", 1033905: "LMNX", 778734: "MEAS", 64670: "MDT",
    944765: "MRGE", 794172: "VIVO", 66479: "MIL", 1373060: "MR", 878526: "BABY", 1142596: "NUVA",
    711665: "PHMD", 1398090: "PMII", 1171298: "SLTM", 789132: "SPNC", 203077: "STJ", 815065: "STE",
    1314772: "SUMR", 1292055: "SMA", 1291361: "ELOS", 350907: "THOR", 1010610: "TLCV", 885590: "VRX",
    203527: "VAR", 865846: "VITL", 887568: "ZOLL", 1135644: "SI", 1160110: "VE", 16988: "CAJ",
    19446: "CMN", 820237: "GPRO", 1322232: "COA", 1305773: "CFMS", 1162461: "CUTR", 1628945: "HLTH",
    742112: "IVC", 937556: "MASI", 859737: "HOLX", 1551693: "SIEN", 1453593: "BONE", 1269026: "AMDA",
    1607962: "RWLK", 31791: "PKI", 1015820: "QGEN", 882835: "ROP", 1067983: "BRK.A / BRK.B",
    55785: "KMB", 67887: "MOG.A / MOG.B", 1639691: "LIVN", 1333141: "FMS", 845982: "SNN",
    313216: "PHG", 1114448: "NVS", 938323: "PSO", 1816708: "OWLT", 866374: "FLEX", 2046386: "MDLN",
}
# US EXCHANGE LISTING of each linked issuer's COMMON STOCK / ADS.
# EDGAR registration forms cannot settle this mechanically: many Nasdaq firms
# registered under 12(g) (Nasdaq only became a registered exchange in 2006),
# and Form 25/15 filings often concern debt, warrants or redomiciles (e.g.
# Covidien 2009, Invacare notes 2015). So the exchange is recorded here, with
# a dated window only where the stock itself joined or left an exchange
# inside the sample (dates = the 8-A12B / Form 25 filing for the stock).
# Whether the issuer was public at all on the letter date (not yet IPO'd,
# acquired, deregistered) is still tested from EDGAR in listing_status().
NASDAQ = [881890, 815094, 1037760, 1374128, 354908, 1389072, 849448, 1033905, 778734, 944765,
          794172, 878526, 1142596, 711665, 1398090, 1171298, 789132, 1314772, 1291361, 350907,
          865846, 887568, 820237, 1322232, 1305773, 1162461, 1628945, 937556, 859737, 1551693,
          1607962, 1639691, 1097149, 1350653, 1275187, 1488039, 1674632, 1093557, 1840877,
          1145197, 1035267, 883984, 917520, 1158895, 1393434, 1484612, 718937, 1388658, 818479,
          1003130, 1010610, 724004, 884624, 1116463, 856982, 1039065, 866374, 897723, 1015820,
          816956, 1716166, 1269026, 2046386, 1196298, 704440]
NYSE = [1168335, 1145460, 1578845, 784199, 9892, 840467, 1457543, 1385187, 47518, 1274057, 895655,
        831967, 64670, 66479, 1373060, 203077, 815065, 1292055, 885590, 203527, 1135644, 1160110,
        16988, 19446, 742112, 31791, 882835, 1067983, 55785, 67887, 1333141, 845982, 313216,
        1114448, 938323, 1816708, 66740, 1800, 200406, 10456, 313616, 711404, 1551152, 1555280,
        40545, 51143, 10795, 310764, 1099800, 721371, 1090872, 12208, 885725, 313927, 1237831,
        1321732, 920148, 313143, 1613103, 1136869, 1606498]
LISTING = {c: [(LO, HI, "Nasdaq")] for c in NASDAQ}
LISTING.update({c: [(LO, HI, "NYSE")] for c in NYSE})
LISTING.update({
    741815: [(LO, "2017-05-01", "NYSE MKT")],             # Hooper Holmes
    1453593: [("2010-11-05", HI, "NYSE MKT")],            # Bacterin / Xtant
    1010610: [(LO, "2010-01-08", "Nasdaq")],              # TLC Vision: delisted after Ch.11 filing
    1196298: [("2004-08-27", "2009-04-07", "NYSE Amex"), ("2019-08-13", HI, "Nasdaq")],  # Nephros: OTC 2009-2019
    704440: [("2019-10-15", HI, "Nasdaq")],               # Repro-Med (KORU): OTC before uplisting
    1628945: [("2021-09-20", "2024-06-28", "Nasdaq")],    # Cue Health
    742112: [(LO, "2023-02-16", "NYSE")],                 # Invacare
    16988: [(LO, "2023-02-24", "NYSE")],                  # Canon ADS
    1135644: [(LO, "2014-05-05", "NYSE")],                # Siemens ADS
    1160110: [(LO, "2014-12-12", "NYSE")],                # Veolia ADS
    1015820: [(LO, "2018-01-01", "Nasdaq"), ("2018-01-01", HI, "NYSE")],  # Qiagen moved to NYSE in 2018
    816956: [(LO, "2020-01-01", "Nasdaq"), ("2020-01-01", HI, "NYSE")],   # CONMED moved to NYSE ~2020
    711404: [(LO, "2023-01-01", "NYSE"), ("2023-01-01", HI, "Nasdaq")],   # Cooper Cos. moved to Nasdaq
    55785: [(LO, "2024-01-01", "NYSE"), ("2024-01-01", HI, "Nasdaq")],    # Kimberly-Clark moved to Nasdaq
    882835: [(LO, "2023-01-01", "NYSE"), ("2023-01-01", HI, "Nasdaq")],   # Roper moved to Nasdaq
})
# Reporting companies whose stock traded only OTC in the sample (no exchange listing):
# Arrayit, BioElectronics, Kelyniam, ZYTO, Non-Invasive Monitoring Systems, OxySure, UV Flu.


# =============================================================
# STEP 2. SEC EDGAR filing histories (cached)
# =============================================================
PERIODIC = {"10-K", "10-K405", "10-KSB", "10-KSB40", "10-Q", "10-QSB", "20-F", "40-F", "10-KT"}
EXREG = {"8-A12B", "8-A12B/A", "10-12B", "10-12B/A", "8-B12B"}
DEREG = {"15-12B", "15-12G", "15-15D", "15F-12B", "15F-12G", "15F-15D"}
IPO_REG = {"S-1", "F-1", "424B4", "424B1"}
OTCREG = {"8-A12G", "10-12G"}
DELIST = {"25", "25-NSE"}
LISTED_EX = {"NYSE", "Nasdaq", "CBOE", "NYSE MKT", "NYSE American", "NYSE Arca"}


def sec_get(url):
    for attempt in range(4):
        r = requests.get(url, headers=SEC_UA, timeout=60)
        time.sleep(0.15)                      # stay well under SEC's 10 req/s
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"SEC request failed ({r.status_code}): {url}")


def fetch_submissions(cik):
    """Full filing history for one CIK (recent block + older paged files)."""
    path = CACHE_DIR / f"{cik}.json"
    if not path.exists():
        d = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if d is None:
            d = {"missing": True}
        else:
            d["extra"] = [e for f in d["filings"].get("files", [])
                          if (e := sec_get("https://data.sec.gov/submissions/" + f["name"]))]
        path.write_text(json.dumps(d))
    d = json.loads(path.read_text())
    if d.get("missing"):
        return None
    ev = []
    for blk in [d["filings"]["recent"]] + d.get("extra", []):
        ev += [(pd.Timestamp(t), f) for f, t in zip(blk["form"], blk["filingDate"])]
    ev.sort()
    return dict(cik=cik, name=d["name"], sic=str(d.get("sic") or ""), tickers=d.get("tickers", []),
                exchanges=[e for e in d.get("exchanges", []) if e], ev=ev,
                periodic=[t for t, f in ev if f in PERIODIC],
                first_filing=ev[0][0] if ev else None)


def auto_exchange(info, d):
    """
    Rule-based exchange test, used ONLY for the industry universe (STEP 4), where
    ~1,000 issuers cannot be hand-checked. Letter recipients never use it. Known
    approximations: Form 25s for debt can end a listing early for firms no longer
    filing today; firms listed before EDGAR that are listed today count as listed.
    """
    ev = info["ev"]
    exreg = [t for t, f in ev if f in EXREG]
    otcreg_pre2006 = any(f in OTCREG and t < pd.Timestamp("2006-08-01") for t, f in ev)
    delists = [t for t, f in ev if f in DELIST]
    if set(info["exchanges"]) & LISTED_EX:
        on = (any(t <= d for t in exreg) or otcreg_pre2006
              or info["first_filing"] <= pd.Timestamp("1997-12-31"))
        # OTC gap between an exchange delisting and a later re-listing (e.g. Nephros 2009-2019)
        if on and len(exreg) <= 3:
            for t25 in delists:
                if t25 <= d and any(t8 > d and (t8 - t25).days >= 180 for t8 in exreg):
                    on = False
        return on
    # Not exchange-listed today (acquired, dark, or OTC now)
    before = [t for t in exreg if t <= d]
    if before:
        gone = [t for t in delists if before[-1] < t <= d
                and any(u > t + timedelta(days=365) for u in info["periodic"])]   # kept filing = moved to OTC
        return not gone
    # Listed before any 8-A12B on EDGAR (pre-2006 Nasdaq firms registered under 12(g)):
    # a LATER Form 25, with no exchange registration in between, shows the stock
    # was on an exchange on date d.
    later_delisting = any(t > d and not any(d < u < t for u in exreg) for t in delists)
    return later_delisting and (otcreg_pre2006 or info["first_filing"] <= pd.Timestamp("2006-08-01"))


def listing_status(info, d, auto=False):
    """Was this issuer listed on a US exchange on date d? -> (code, evidence[, exchange])."""
    if info is None:
        return "UNCLEAR", "no SEC record found"
    per, ev = info["periodic"], info["ev"]
    if not per:
        return "NO", "SEC filer but never filed 10-K/10-Q/20-F (e.g., Form D only) - not public"
    before = [t for t in per if t <= d]
    ipo = [t for t, f in ev if f in EXREG | IPO_REG and d - timedelta(days=450) <= t <= d]
    if not before and not ipo:
        return "NO", f"not yet public: first periodic report {per[0].date()}"
    lastp = before[-1] if before else None
    dereg = [t for t, f in ev if f in DEREG and t <= d and (lastp is None or t >= lastp - timedelta(days=30))]
    if dereg:
        return "NO", f"no longer public: deregistered (Form 15) {dereg[0].date()}"
    if lastp is not None and (d - lastp).days > 460 and not ipo:
        return "NO", f"no longer public: last periodic report {lastp.date()}"
    last = f"last periodic report {lastp.date()}" if lastp is not None else "IPO registration within the prior 15 months"
    windows = LISTING.get(info["cik"])
    if windows is None and auto:
        if auto_exchange(info, d):
            return "YES", f"SEC-reporting ({last}); exchange-listed per EDGAR registration/delisting record", \
                ", ".join(e for e in info["exchanges"] if e in LISTED_EX) or "US exchange (not identified)"
        return "OTC", f"SEC-reporting ({last}), but no evidence of an exchange listing"
    if windows is None:
        return "OTC", f"SEC-reporting at letter date ({last}), but the stock traded OTC, not on a US exchange"
    for a, b, exch in windows:
        if pd.Timestamp(a) <= d < pd.Timestamp(b):
            return "YES", f"SEC-reporting at letter date ({last}); stock listed on {exch}", exch
    return "OTC", f"SEC-reporting at letter date ({last}), but the stock was not exchange-listed then (OTC)"


# =============================================================
# STEP 3. Apply to every letter
# =============================================================
def _gv(g):
    return str(int(float(g))).zfill(6)


def _co_key(name):
    """Company-name key for gvkey look-ups: drop SEC state tags (/DE/), punctuation and legal forms."""
    s = re.sub(r"/[A-Z]{2}/?", " ", str(name).upper())
    s = re.sub(r"[^A-Z0-9 ]", " ", s.replace("&", " AND "))
    s = re.sub(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|NV|AG|SA|LLC|THE)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cik_to_gvkey():
    """
    cik -> gvkey from the project's existing Compustat-derived files (no WRDS needed):
      1. exact CIK: every project CSV that carries both gvkey and cik;
      2. otherwise exact company NAME: the SEC name equals a Compustat/crosswalk name that maps to
         exactly ONE gvkey (e.g. 'MEDTRONIC INC' = 'Medtronic, Inc.' -> 007228).
    Returns a function cik -> (gvkey, how) ; ('', ...) when not in the project files.
    """
    by_cik, by_name = {}, {}
    # gvkeys entered by hand (e.g. looked up on the WRDS website), with where they came from
    manual_path = RAW_DIR / "compustat_manual_gvkeys.csv"
    manual = {}
    if manual_path.exists():
        m = pd.read_csv(manual_path, dtype=str)
        manual = {int(c): (_gv(g), src) for c, g, src in zip(m.cik, m.gvkey, m.source)}
    files = [f for pat in ("processed/*.csv", "external/*.csv", "raw/*.csv") for f in (RAW_DIR.parent).glob(pat)]
    for f in files:
        try:
            cols = pd.read_csv(f, nrows=0).columns
        except Exception:
            continue
        if "gvkey" not in cols or f.name == manual_path.name:
            continue
        names = [c for c in cols if re.search(r"conm|compustat|company|firm_name", c, re.I)]
        df = pd.read_csv(f, dtype=str, usecols=["gvkey"] + names + (["cik"] if "cik" in cols else []))
        df = df[df.gvkey.fillna("").str.match(r"^\d+(\.0)?$")]
        if "cik" in df:
            for g, c in zip(df.gvkey, df.cik):
                if isinstance(c, str) and re.match(r"^\d+(\.0)?$", c):
                    by_cik.setdefault(int(float(c)), set()).add(_gv(g))
        for n in names:
            for g, nm in zip(df.gvkey, df[n]):
                if isinstance(nm, str):
                    by_name.setdefault(_co_key(nm), set()).add(_gv(g))

    def lookup(cik):
        if cik in manual:
            return manual[cik][0], f"entered by hand: {manual[cik][1]}"
        if cik in by_cik:
            return "; ".join(sorted(by_cik[cik])), "exact SEC ID (CIK) in project Compustat files"
        info = fetch_submissions(cik)
        hit = by_name.get(_co_key(info["name"])) if info else None
        if hit and len(hit) == 1:
            return next(iter(hit)), "exact company-name match in project Compustat files"
        return "", "not in the project's Compustat files - look up in WRDS"
    return lookup


# Tickers that changed inside the sample: cik -> (change date, ticker before)
TICKER_BEFORE = {1136869: ("2015-06-24", "ZMH")}   # Zimmer Holdings -> Zimmer Biomet


# Letter-level corrections found by reading the letters themselves (keyed by FDA
# Case/Injunction ID). The Dashboard shows a firm's CURRENT legal name, which can
# point to a later owner.
CASE_OVERRIDES = {
    617147: "Letter (2021-10-01) went to Smiths Medical ASD, Inc., owned by Smiths Group (listed in London only). "
            "The FDA Dashboard shows the current name 'ICU Medical Inc.', but ICU Medical only acquired Smiths "
            "Medical on 2022-01-06, after the letter",
    147232: "Letter (2011-01-06) is filed under 'Flir System AB' by FDA, but was addressed to Central Coast "
            "Thermography (a private breast-imaging clinic in California) for marketing FLIR cameras for "
            "uncleared uses - FLIR itself was not the recipient",
}


def classify(name, d, gv, case_id=None):
    periods = C.get(name)
    blank = dict(listing_basis="", listed_entity="", parent_company="", ticker="", exchange="",
                 sec_cik="", gvkey="", match_confidence="", evidence="", notes="")
    if case_id in CASE_OVERRIDES:
        return dict(blank, us_listed_at_letter="No", notes=CASE_OVERRIDES[case_id])
    if name in UNCLEAR_NAMES and (name != "TEI Biosciences, Inc." or d < pd.Timestamp("2015-07-01")):
        return dict(blank, us_listed_at_letter="Unclear", notes=UNCLEAR_NAMES[name])
    if not periods:
        return dict(blank, us_listed_at_letter="No",
                    notes=NOTE_NO.get(name, "No link to a US-listed company (private, individual, institution, or non-US-listed firm)"))
    hit = [p for p in periods if pd.Timestamp(p[0]) <= d < pd.Timestamp(p[1])]
    if not hit:
        note = "; ".join(p[6] for p in periods if p[6]) or "outside the ownership window of any US-listed issuer"
        return dict(blank, us_listed_at_letter="No", notes=note)
    a, b, cik, rel, label, conf, note = hit[0]
    info = fetch_submissions(cik)
    code, evidence, *exch = listing_status(info, d)
    status = {"YES": "Yes", "NO": "No", "OTC": "No", "UNCLEAR": "Unclear"}[code]
    if status == "Yes" and rel == "parent":
        status = "Yes - via parent"
    return dict(
        us_listed_at_letter=status,
        listing_basis="Recipient itself" if rel == "self" else "Parent company",
        listed_entity=(info or {}).get("name", ""),
        parent_company=label if rel == "parent" else "",
        ticker=(TICKER_BEFORE[cik][1] if cik in TICKER_BEFORE and d < pd.Timestamp(TICKER_BEFORE[cik][0])
                else TICKER_AT.get(cik) or next(iter((info or {}).get("tickers", [])), "")),
        exchange=exch[0] if exch else ("OTC" if code == "OTC" else ""),
        sec_cik=str(cik), gvkey=gv(cik)[0], match_confidence=conf,
        evidence=evidence, notes=note)


# =============================================================
# STEP 4. Industry benchmark: US-listed medical-device companies per year
# =============================================================
# Universe = every SEC registrant whose EDGAR SIC code is in DEVICE_SICS: the
# project's device filter 3841-3845 (scripts 08/09/18) PLUS 3851 ophthalmic goods,
# 2835 in-vitro diagnostics and 3826 laboratory analytical instruments (added
# 2026-09-27 at Armando's request, so device-type firms filed under neighboring
# codes - Cooper, STAAR, Cepheid, Alere - are counted). Counted in year Y if it was
# listed on a US exchange at ANY point in Y (checked at each month-end).
# Hand-checked issuers use their LISTING windows; all others use auto_exchange().
DEVICE_SICS = ("3841", "3842", "3843", "3844", "3845", "3851", "2835", "3826")
SIC_NAMES = {"3841": "Surgical & Medical Instruments & Apparatus",
             "3842": "Orthopedic, Prosthetic & Surgical Appliances & Supplies",
             "3843": "Dental Equipment & Supplies", "3844": "X-Ray Apparatus & Tubes",
             "3845": "Electromedical & Electrotherapeutic Apparatus", "3851": "Ophthalmic Goods",
             "2835": "In Vitro & In Vivo Diagnostic Substances", "3826": "Laboratory Analytical Instruments"}
SIC_TEXT = ", ".join(DEVICE_SICS)
# SIC 3826 (laboratory analytical instruments) mixes clinical-diagnostics makers with
# research-tool and industrial instrument makers (Waters, Mettler-Toledo, Bruker,
# 10x Genomics, ...). Only the 3826 companies below - reviewed by hand (2026-09-27),
# each making FDA-regulated in-vitro diagnostic products - count as device companies.
# Agilent (Dako diagnostics) and Millipore were added at Armando's request: both
# received device warning letters in the sample.
SIC_3826_DIAGNOSTICS = {
    12208: "Bio-Rad Laboratories", 31791: "PerkinElmer / Revvity", 319240: "IRIS International",
    727207: "Accelerate Diagnostics", 840467: "Beckman Coulter", 1037760: "Cepheid",
    1043961: "Precipio", 1083132: "Immunicon", 1110803: "Illumina", 1169987: "HTG Molecular Diagnostics",
    1584751: "Talis Biomedical", 1628945: "Cue Health", 1090872: "Agilent Technologies", 66479: "Millipore",
}
SIC_TEXT_FULL = SIC_TEXT.replace("3826", "3826 (diagnostics makers only)")
SIC_LIST_CACHE = RAW_DIR / "edgar_device_sic_ciks.json"


def device_sic_ciks():
    """{cik: sic} for all EDGAR companies with a DEVICE_SICS code (cached; missing codes are fetched)."""
    cache = json.loads(SIC_LIST_CACHE.read_text()) if SIC_LIST_CACHE.exists() else {}
    if "ciks" not in cache:                                   # first cache format: {cik: sic}
        cache = {"sics": sorted(set(cache.values())), "ciks": cache}
    todo = [s for s in DEVICE_SICS if s not in cache["sics"]]
    if todo:
        out = cache["ciks"]
        for sic in todo:
            start = 0
            while True:
                url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC={sic}"
                       f"&owner=include&count=100&start={start}&output=atom")
                for attempt in range(5):
                    try:
                        r = requests.get(url, headers=SEC_UA, timeout=90)
                        if r.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(5 * (attempt + 1))
                ciks = re.findall(r"<cik>(\d+)</cik>", r.text)
                out.update({str(int(c)): sic for c in ciks if str(int(c)) not in out})
                time.sleep(0.3)
                if len(ciks) < 100:
                    break
                start += 100
        cache = {"sics": sorted(set(cache["sics"]) | set(todo)), "ciks": out}
        SIC_LIST_CACHE.write_text(json.dumps(cache))
    return {int(k): v for k, v in cache["ciks"].items()
            if v in DEVICE_SICS and (v != "3826" or int(k) in SIC_3826_DIAGNOSTICS)}


def universe_by_year(years):
    """Long table: one row per (device-SIC company, year) listed on a US exchange."""
    rows = []
    for cik, sic in device_sic_ciks().items():
        info = fetch_submissions(cik)
        if info is None or not info["periodic"]:
            continue
        for y in years:
            checks = [d for d in (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0) for m in range(1, 13))
                      if d <= pd.Timestamp.today()]
            for d in checks:
                code, evidence, *exch = listing_status(info, d, auto=True)
                if code == "YES":
                    rows.append(dict(year=y, sec_cik=cik, company=info["name"], sic=sic,
                                     exchange=exch[0] if exch else "",
                                     hand_checked=cik in LISTING, evidence=evidence))
                    break
    return pd.DataFrame(rows)


def yearly_comparison(out, universe):
    out = out.assign(year=out["Action Taken Date"].dt.year)
    listed = out[out.us_listed_at_letter.str.startswith("Yes")]
    uni = universe.groupby("year").sec_cik.apply(set)
    rows = []
    for y in sorted(out.year.unique()):
        ly = listed[listed.year == y]
        firms = set(ly.sec_cik.astype(int))
        u = uni.get(y, set())
        rows.append({
            "Year": y,
            "Warning letters (all)": int((out.year == y).sum()),
            "Letters to US-listed companies": len(ly),
            "US-listed companies receiving letters (sample)": len(firms),
            "  of which the recipient itself": ly[ly.listing_basis == "Recipient itself"].sec_cik.nunique(),
            "  of which via a US-listed parent": ly[ly.listing_basis == "Parent company"].sec_cik.nunique(),
            f"Sample companies with a device SIC ({SIC_TEXT})": len(firms & u),
            f"US-listed medical-device companies (SIC {SIC_TEXT})": len(u),
            "Sample device companies as % of device universe": round(100 * len(firms & u) / len(u), 1) if u else None,
        })
    return pd.DataFrame(rows)


# =============================================================
# STEP 5. Simple summary workbook: one row per year + how the data was pulled
# =============================================================
UNIVERSE_SOURCE = (f"SEC EDGAR company database - all companies with SEC industry (SIC) codes "
                   f"{SIC_TEXT_FULL}, checked against each company's EDGAR filing history")
def year_comment(y, n_letters, unclear, uni_y, first, last):
    notes = []
    if y == first.year:
        notes.append(f"Partial year: the FDA file starts {first:%b %d, %Y}.")
    if y == last.year:
        notes.append(f"Partial year: the FDA file ends {last:%b %d, %Y}.")
    if y == 2016:
        notes.append("Letter counts drop sharply from 2016 on; this reflects fewer FDA letters overall, not a data gap.")
    if unclear:
        notes.append(f"{unclear} letter(s) this year could not be confirmed as going to a publicly traded company (marked Unclear).")
    if len(uni_y):
        auto = int((~uni_y.hand_checked).sum())
        notes.append(f"Industry total: {len(uni_y) - auto} companies hand-checked, {auto} classified by an automatic "
                     f"filing-based rule ({100 * auto / len(uni_y):.0f}%); the rule-based part is approximate.")
    return " ".join(notes)


# Publicly traded recipients whose letters cite them as device USERS (clinics that
# must report adverse events), not as device makers/sellers. FDA's Oct-2009 LASIK
# sweep: letters to LasikPlus / TLC centers for inadequate adverse-event (MDR)
# reporting. Kept in column 1 (all letters) but excluded from columns 3-5.
DEVICE_USER_ONLY = {
    1003130: "LCA-Vision (LasikPlus LASIK clinics)",
    1010610: "TLC Vision (TLC Laser Eye Centers)",
}

# Kept in columns 3-5 for now, but NOT yet confirmed as a device maker/seller letter.
# TODO: when the full warning-letter texts are downloaded, read these letters and
# move the company to DEVICE_USER_ONLY if the letter cites it as a device user.
TO_VERIFY = {
    920148: "Labcorp ('Labcorp- PMD', 2011): kept in columns 4-5, but the letter has not been read to confirm "
            "Labcorp was cited as a device maker/seller rather than a lab using devices - verify when all "
            "warning letters are downloaded",
}

COL_LETTERS = ("1. Warning letters issued (all FDA device warning letters; public and private recipients; each "
               "letter counted once even if it covers several facilities)")
COL_UNIVERSE = (f"2. US publicly traded medical device companies (SEC industry codes {SIC_TEXT_FULL}; listed on NYSE, "
                "Nasdaq, NYSE American or Cboe at any point in the year)")
COL_DEVICE_HIT = ("3. Publicly traded medical device companies (from column 2) that received a letter, "
                  "directly or through a subsidiary - unique companies")
COL_ALL_HIT = ("4. All publicly traded medical device companies, or parents of a medical device subsidiary, that "
               "received a letter - unique companies; includes column 3 plus diversified parents such as J&J, Abbott, "
               "Danaher (excludes LASIK clinic chains cited only as device users)")
COL_ALL_LETTERS = ("5. Warning letters received by the column 4 companies as medical device makers/sellers - total "
                   "letters, so a company (or its device subsidiaries) with several letters in the year counts once in "
                   "column 4 but every letter counts here")
COL_EXCLUDED = ("6. Warning letters NOT in column 5 - letters to private or non-US-listed companies, unconfirmed "
                "recipients, and LASIK clinic chains (column 5 + column 6 = column 1; see footnote 1)")
COL_VIA_SUB = "Column 4 companies counted through a subsidiary (parent company: subsidiary that received the letter)"
COL_SOURCE = "Source of column 2 (medical device company total)"
COL_NOTES = "Data certainty comments"


def summary_by_year(out, universe):
    out = out.assign(year=out["Action Taken Date"].dt.year)
    yes_all = out[out.us_listed_at_letter.str.startswith("Yes")].assign(cik=lambda x: x.sec_cik.astype(int))
    user = yes_all[yes_all.cik.isin(DEVICE_USER_ONLY)]
    yes = yes_all[~yes_all.cik.isin(DEVICE_USER_ONLY)]
    first, last = out["Action Taken Date"].min(), out["Action Taken Date"].max()
    rows, dev_all, pub_all = [], set(), set()
    for y in sorted(out.year.unique()):
        oy, yy = out[out.year == y], yes[yes.year == y]
        uni_y = universe[universe.year == y]
        pub = set(yy.cik)                              # every listed company hit, itself or via a subsidiary
        dev = pub & set(uni_y.sec_cik)                 # ...that is itself in the device-code universe
        dev_all |= dev
        pub_all |= pub
        via = yy[yy.listing_basis == "Parent company"]
        via_txt = [f"EXCLUDED from columns 3-5: {DEVICE_USER_ONLY[c]} - {len(g)} letter(s) to LASIK clinics, which use "
                   f"medical devices but do not make or sell them"
                   for c, g in user[user.year == y].groupby("cik")]
        for cik, g in via.groupby("cik"):
            parent = f"{g.parent_company.iloc[0]} ({g.ticker.iloc[0]})"
            tag = "" if cik in dev else " [not in the device codes, so not in column 3]"
            via_txt.append(f"{parent}{tag}: " + ", ".join(sorted(set(g["Legal Name"]))))
        n_letters_y = oy["Case/Injunction ID"].nunique()          # distinct letters, not facility rows
        n_col5_y = yy["Case/Injunction ID"].nunique()
        rows.append({
            "Year": int(y),
            COL_LETTERS: n_letters_y,
            COL_UNIVERSE: uni_y.sec_cik.nunique(),
            COL_DEVICE_HIT: len(dev),
            COL_ALL_HIT: len(pub),
            COL_ALL_LETTERS: n_col5_y,
            COL_EXCLUDED: n_letters_y - n_col5_y,
            COL_VIA_SUB: " | ".join(sorted(via_txt)),
            COL_SOURCE: UNIVERSE_SOURCE,
            COL_NOTES: " ".join([year_comment(y, len(oy), int((oy.us_listed_at_letter == "Unclear").sum()),
                                              uni_y, first, last)]
                                + [f"TO VERIFY: {TO_VERIFY[c]}." for c in sorted(set(yy.cik) & set(TO_VERIFY))]),
        })
    df = pd.DataFrame(rows)
    n_years = len(df)
    df.loc[len(df)] = {
        "Year": "Total: sum of the years", COL_LETTERS: df[COL_LETTERS].sum(), COL_UNIVERSE: df[COL_UNIVERSE].sum(),
        COL_DEVICE_HIT: df[COL_DEVICE_HIT].sum(), COL_ALL_HIT: df[COL_ALL_HIT].sum(),
        COL_ALL_LETTERS: df[COL_ALL_LETTERS].sum(), COL_EXCLUDED: df[COL_EXCLUDED].sum(), COL_VIA_SUB: "", COL_SOURCE: "",
        COL_NOTES: (f"Adds the {n_years} yearly rows. For columns 2-4 this counts company-YEARS: a company public in "
                    f"all {n_years} years is counted {n_years} times.")}
    df.loc[len(df)] = {
        "Year": "Total: unique companies, 2008-2026", COL_LETTERS: df.loc[n_years, COL_LETTERS],
        COL_UNIVERSE: universe.sec_cik.nunique(), COL_DEVICE_HIT: len(dev_all), COL_ALL_HIT: len(pub_all),
        COL_ALL_LETTERS: df.loc[n_years, COL_ALL_LETTERS], COL_EXCLUDED: df.loc[n_years, COL_EXCLUDED],
        COL_VIA_SUB: "", COL_SOURCE: "",
        COL_NOTES: (f"Counts each company ONCE no matter how many years it appears. Column 2: "
                    f"{universe.sec_cik.nunique()} different medical device companies were US publicly traded at some "
                    f"point in the period; the yearly totals (about "
                    f"{df[COL_UNIVERSE].iloc[:n_years].min()}-{df[COL_UNIVERSE].iloc[:n_years].max()}) are how many were listed in each "
                    f"individual year, as companies IPO, get acquired or delist. Letters are already one per row, so "
                    f"columns 1, 5 and 6 are the same in both total rows.")}
    return df


def how_data_was_pulled(out, today):
    y0, y1 = out["Action Taken Date"].min(), out["Action Taken Date"].max()
    rows = [
        ("1. Warning letters", "Database", "FDA Data Dashboard - Compliance Actions (datadashboard.fda.gov/oii/cd/complianceactions.htm)"),
        ("", "Filters used", "Product Type = Devices;  Action Type = Warning Letter"),
        ("", "What we got", f"{out['Case/Injunction ID'].nunique():,} warning letters ({len(out):,} rows in the FDA file: a "
                            f"letter covering several facilities appears once per facility, so letters are counted by "
                            f"their FDA case number) dated {y0:%b %d, %Y} to {y1:%b %d, %Y}, counted by the year of the 'Action Taken Date'."),
        ("2. US publicly traded medical device companies", "Database", "SEC EDGAR (www.sec.gov/edgar), the SEC's public filing database"),
        ("", "Industry codes used", ";  ".join(f"SIC {c} {SIC_NAMES[c]}" for c in DEVICE_SICS)
                                    + ". Codes 3841-3845 are the project's core device codes; 3851, 2835 and 3826 were "
                                      "added so device-type companies the SEC files under neighboring codes are counted "
                                      "(e.g., Cooper Companies and STAAR Surgical under 3851; Cepheid and Alere under "
                                      "2835/3826). Code 3826 (laboratory analytical instruments) also covers research-tool "
                                      "and industrial instrument makers, so only the 3826 companies that make clinical "
                                      "diagnostics are counted: " + ", ".join(sorted(SIC_3826_DIAGNOSTICS.values()))
                                    + ". Excluded from 3826, e.g.: Waters, Mettler-Toledo, Bruker, Coherent, "
                                      "10x Genomics, Pacific Biosciences, Avantor."),
        ("", "Stock exchanges counted", "NYSE, Nasdaq, NYSE American (formerly AMEX / NYSE MKT), Cboe. Over-the-counter (OTC) "
                                        "stocks and companies listed only outside the US are not counted."),
        ("", "SEC filings used", "10-K, 10-Q, 20-F, 40-F (annual/quarterly reports = the company was public);  Form 8-A12B "
                                 "(registered a stock on an exchange);  Form 25 (removed from an exchange);  Form 15 "
                                 "(stopped reporting)."),
        ("", "How a company is counted", "Counted in a year if, at any month-end that year, it was filing annual/quarterly "
                                         "reports AND its stock was listed on one of the exchanges above."),
        ("3. Matching letters to public companies", "Method", "Every recipient name was reviewed by hand and linked to the "
                                                               "SEC record of the company itself or of its publicly traded "
                                                               "parent, using acquisition dates (e.g., Beckman Coulter -> "
                                                               "Danaher from mid-2011)."),
        ("", "Column 3", "A publicly traded device company (from step 2) is counted once per year if it, or one of "
                         "its subsidiaries, received at least one letter while it was publicly traded."),
        ("", "Column 4", "Every publicly traded company counted once per year if it, or one of its medical device "
                         "subsidiaries, received at least one letter while it was publicly traded - including large "
                         "diversified companies that the SEC does not classify as device companies (e.g., Johnson & "
                         "Johnson, Abbott, Danaher, Novartis, Kimberly-Clark), provided the letter went to a subsidiary that makes "
                         "or sells medical devices. The comments column "
                         "names the parent and the subsidiary for each company counted through a subsidiary."),
        ("", "Device makers/sellers only", "Every letter in the FDA file is a device letter, but a few went to "
                         "companies as device USERS rather than makers or sellers: LASIK clinic chains (LasikPlus / "
                         "LCA-Vision in 2009, 2010 and 2012; TLC Vision in 2009), e.g. the FDA's October 2009 letters "
                         "to LASIK clinics for not reporting adverse events. "
                         "Those letters stay in column 1 but are excluded from columns 3-5, and are listed in the "
                         "comments column. All other publicly traded recipients make or sell medical devices."),
        ("", "Still to verify", "; ".join(TO_VERIFY.values()) + "."),
        ("", "Column 5", "The total number of warning letters that went to the column 4 companies (directly or to "
                         "their device subsidiaries) that year. Column 4 counts each company once; column 5 counts "
                         "every letter, so it is higher when a company or its subsidiaries got more than one letter."),
        ("", "Diversified parents and column 2", "Column 2 counts publicly traded COMPANIES, and a subsidiary does "
                         "not trade on its own - it is part of its parent. So when the parent has a non-device SEC code "
                         "(e.g., Johnson & Johnson and Abbott are classified as pharmaceutical, Danaher as industrial "
                         "instruments), neither the parent nor its device subsidiaries (e.g., DePuy, Abbott Diabetes "
                         "Care, Beckman Coulter) are in column 2. Their letters ARE counted: the parent appears in "
                         "column 4 and every letter to its device subsidiaries in column 5, with the subsidiary named "
                         "in the comments column. Parents whose SEC code IS a device code (e.g., Medtronic, Philips, "
                         "Baxter) are in column 2 and in columns 3-5."),
        ("All letters with gvkey tab", "What it shows", "One row per warning letter (all letters in column 1), with the "
                         "company that received it, whether it was publicly traded in the US on the letter date, the "
                         "publicly traded company (itself or parent), ticker and Compustat gvkey. gvkeys come from the "
                         "project's existing Compustat-derived files (matched by SEC ID, or by exact company name to a "
                         "single gvkey). Private and non-US-listed recipients have no gvkey; a few publicly traded "
                         "companies are marked 'look up in WRDS' because they are not in the project files yet."),
        ("", "Column 6", "Letters in column 1 that are not in column 5, so column 5 + column 6 = column 1 (see "
                         "footnote 1 on the summary tab for the breakdown)."),
        ("", "Two total rows", "'Sum of the years' adds the yearly rows (company-years). 'Unique companies' counts "
                               "each company once across 2008-2026, which is why it is smaller."),
        ("", "Known limitations", "The SEC assigns each company ONE current industry code, so a company that changed "
                                  "industries is classified by today's code for every year. About "
                                  "a third of the companies were checked by hand; the rest use an automatic rule based on "
                                  "their SEC filings, so yearly totals are approximate."),
        ("4. To repeat", "Steps", "1) Download a new FDA export with the filters above and save it as "
                                  "data/raw/Copy_FDA Warning Letter_Data.xlsx.  2) Run scripts/19_warning_letter_us_listing_status.py.  "
                                  "3) Review any new recipient names and add them to the script's company list."),
        ("", "Built", f"{today}"),
    ]
    return pd.DataFrame(rows, columns=["Step", "Item", "Detail"])


def summary_footnotes(out, universe):
    """Footnotes printed under the summary table (computed, so they stay true on re-runs)."""
    yes = out[out.us_listed_at_letter.str.startswith("Yes")].assign(cik=lambda x: x.sec_cik.astype(int))
    # classify each distinct LETTER (a letter can span several facility rows)
    def letter_group(g):
        pub = g.us_listed_at_letter.str.startswith("Yes")
        lasik = pd.to_numeric(g.sec_cik, errors="coerce").fillna(0).astype(int).isin(DEVICE_USER_ONLY)
        if (pub & ~lasik).any():
            return "col5"
        if (pub & lasik).any():
            return "lasik"
        return "unclear" if (g.us_listed_at_letter == "Unclear").any() else "no"
    grp = out.groupby("Case/Injunction ID").apply(letter_group).value_counts()
    n_letters = out["Case/Injunction ID"].nunique()
    n_col5, n_lasik, n_unclear, n_no = (int(grp.get(k, 0)) for k in ("col5", "lasik", "unclear", "no"))
    per_letter = out.groupby("Case/Injunction ID").apply(letter_group)
    in_codes = set(universe.sec_cik)
    def label(g):          # name as of the letter: the parent's label, or the recipient's own name
        par = g[g.parent_company.fillna("") != ""]
        return par.parent_company.iloc[0] if len(par) else g["Legal Name"].iloc[0]
    outside = sorted((label(g), fetch_submissions(c)["sic"]) for c, g in yes.groupby("cik")
                     if c not in in_codes and c not in DEVICE_USER_ONLY)
    return [
        "Footnotes",
        (f"1. Column 6 (letters not in column 5): column 6 = column 1 - column 5, so every letter is accounted for. "
         f"All years together: {n_letters:,} letters issued (column 1) = {n_col5:,} letters to publicly traded medical "
         f"device companies or their device subsidiaries (column 5) + {n_letters - n_col5:,} letters in column 6. "
         f"Column 6 is made up of: {n_no:,} letters to companies that were not publicly traded in the US on the letter "
         f"date (private companies, doctors, hospitals and review boards, companies listed only outside the US or "
         f"traded only over-the-counter, and companies before their IPO or after being acquired); {n_unclear} letters "
         f"whose recipient could not be confirmed (marked Unclear); and {n_lasik} letters to publicly traded LASIK "
         f"clinic chains (LCA-Vision, TLC Vision), which use medical devices but do not make or sell them. "
         f"Column 2 counts companies, not letters, so it is not part of this letter reconciliation."),
        (f"2. What column 2 (US publicly traded medical device companies) does NOT include: it counts only companies "
         f"that are themselves publicly traded on a US exchange AND classified by the SEC under a medical device code "
         f"({SIC_TEXT_FULL}). Not included: (a) publicly traded companies whose SEC code is NOT one of these codes, "
         f"together with their device subsidiaries (a subsidiary is part of its parent and does not trade on its own) "
         f"- mainly large diversified parents such as Johnson & Johnson and Abbott (coded as pharmaceutical) and "
         f"Danaher (coded as industrial instruments). Of the companies in column 4, {len(outside)} are in this group: "
         + "; ".join(f"{n} (SIC {sic})" for n, sic in outside)
         + ". Their letters ARE counted in columns 4 and 5 (e.g., Johnson & Johnson for letters to DePuy, Acclarent, "
         f"etc.). (b) Private medical device companies. (c) Companies traded only over-the-counter or listed only "
         f"outside the US. (d) Companies in years before they went public or after they were acquired or delisted."),
    ] + pdf_footnote(per_letter)


def pdf_footnote(per_letter):
    """Footnote 3: how the PDF download (script 20) scope reconciles to column 5, from its latest log."""
    logs = sorted(PROCESSED_DIR.glob("warning_letter_pdf_log_*.xlsx"))
    if not logs:
        return []
    log = pd.read_excel(logs[-1])
    group = log.case_id.map(per_letter)
    n_scope, n5 = len(log), int((group == "col5").sum())
    n_lasik = int((group == "lasik").sum())
    later = log[group.isin(["no", "unclear"])]
    later_txt = "; ".join(f"FDA case {c} ({n.split(' | ')[0]}): {CASE_OVERRIDES.get(c, 'reclassified')}"
                          for c, n in zip(later.case_id, later.recipient_names))
    found = log.groupby(group).found.apply(lambda s: int((s == "Yes").sum()))
    return [
        (f"3. Warning-letter PDFs vs. column 5: the PDF copies of the letters (downloaded by script 20; see "
         f"{logs[-1].name} and the shareable zip) cover {n_scope} letters - every letter that went to a publicly "
         f"traded company or its subsidiary at the time of the download. That is more than the {n5} letters in "
         f"column 5 because it also includes: (a) {n_lasik} letters to the LASIK clinic chains LCA-Vision and TLC "
         f"Vision, kept in the download on purpose so their exclusion could be checked (the letters confirm FDA "
         f"treated these clinics as device USERS); and (b) {len(later)} letter(s) excluded after the download, once "
         f"reading the letter showed a different recipient: {later_txt}. Both groups are counted in column 6. "
         f"PDFs were found for {int(found.get('col5', 0))} of the {n5} column-5 letters, "
         f"{int(found.get('lasik', 0))} of the {n_lasik} LASIK letters and "
         f"{int(found.get('no', 0)) + int(found.get('unclear', 0))} of the {len(later)} later-excluded letter(s); "
         f"the rest were not posted online by FDA or not saved by the Internet Archive."),
    ]


def letters_tab(out, gv):
    """One row per distinct warning letter (FDA case #) with recipient name(s) and gvkey."""
    rank = {"Yes": 0, "Yes - via parent": 1, "Unclear": 2, "No": 3}
    rows = []
    for case, g in out.groupby("Case/Injunction ID"):
        g = g.assign(r=g.us_listed_at_letter.map(rank)).sort_values("r")
        top = g.iloc[0]
        status = top.us_listed_at_letter
        cik = int(float(top.sec_cik)) if status.startswith("Yes") and str(top.sec_cik) not in ("", "nan") else None
        if cik in DEVICE_USER_ONLY:
            col5 = "No - LASIK clinic (device user, not maker/seller)"
        elif status.startswith("Yes"):
            col5 = "Yes"
        else:
            col5 = "No"
        gvkey, how = gv(cik) if cik else ("", "not publicly traded in the US on the letter date - no gvkey assigned"
                                          if status == "No" else "recipient not confirmed (Unclear)")
        rows.append({
            "FDA case #": int(case),
            "Letter date": top["Action Taken Date"].date(),
            "Year": top["Action Taken Date"].year,
            "Company that received the letter (FDA name)": " | ".join(sorted(set(g["Legal Name"]))),
            "Country": " | ".join(sorted(set(g["Country/Area"].astype(str)))),
            "Publicly traded in the US on the letter date?": status,
            "Counted in column 5?": col5,
            "Publicly traded company (the recipient itself or its parent)":
                (top.parent_company or top.listed_entity) if status.startswith("Yes") else "",
            "Ticker": top.ticker if status.startswith("Yes") else "",
            "gvkey (Compustat)": gvkey,
            "gvkey note": how if not gvkey else how.replace(" - look up in WRDS", ""),
            "Notes": top.notes,
        })
    return pd.DataFrame(rows).sort_values(["Letter date", "FDA case #"])


def write_summary_workbook(out, universe, today, gv):
    from openpyxl.styles import Alignment, Font

    summ = summary_by_year(out, universe)
    how = how_data_was_pulled(out, today)
    path = PROCESSED_DIR / f"warning_letters_summary_by_year_{today}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary by year", index=False)
        how.to_excel(xw, sheet_name="How the data was pulled", index=False)
        lt = letters_tab(out, gv)
        lt.to_excel(xw, sheet_name="All letters with gvkey", index=False)
        for name, widths in [("Summary by year", [16, 16, 24, 24, 26, 26, 26, 80, 40, 70]),
                             ("How the data was pulled", [32, 24, 110]),
                             ("All letters with gvkey", [11, 12, 7, 45, 16, 18, 22, 38, 10, 11, 40, 60])]:
            ws = xw.book[name]
            ws.freeze_panes = "A2"
            for i, w in enumerate(widths, start=1):
                ws.column_dimensions[ws.cell(1, i).column_letter].width = w
            for row in ws.iter_rows():
                for c in row:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
            for c in ws[1]:
                c.font = Font(bold=True)
        ws = xw.book["Summary by year"]
        for r in (len(summ), len(summ) + 1):
            for c in ws[r]:
                c.font = Font(bold=True)
        ws.row_dimensions[1].height = 105
        r0 = ws.max_row + 2
        for i, text in enumerate(summary_footnotes(out, universe)):
            ws.merge_cells(start_row=r0 + i, start_column=1, end_row=r0 + i, end_column=10)
            c = ws.cell(r0 + i, 1, text)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.font = Font(bold=(i == 0), italic=(i > 0))
            ws.row_dimensions[r0 + i].height = 15 if i == 0 else 15 * (len(text) // 230 + 1)
    print(summ.iloc[:, :7].set_axis(['Year', '1', '2', '3', '4', '5', '6'], axis=1).to_string(index=False))
    print(f"  -> {path.relative_to(REPO_ROOT)}")


def main():
    today = date.today().isoformat()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    letters = pd.read_excel(INPUT_XLSX, sheet_name=INPUT_SHEET)
    print(f"  {len(letters):,} letters, {letters['Legal Name'].nunique():,} distinct recipients")
    gv = cik_to_gvkey()
    res = pd.DataFrame([classify(n, pd.Timestamp(d), gv, int(c))
                        for n, d, c in zip(letters["Legal Name"], letters["Action Taken Date"],
                                           letters["Case/Injunction ID"])])
    out = pd.concat([letters.reset_index(drop=True), res], axis=1)

    firms = (out.groupby("Legal Name")
                .agg(n_letters=("Action Taken Date", "size"),
                     first_letter=("Action Taken Date", "min"), last_letter=("Action Taken Date", "max"),
                     status_values=("us_listed_at_letter", lambda s: " | ".join(sorted(set(s)))),
                     n_letters_listed=("us_listed_at_letter", lambda s: s.str.startswith("Yes").sum()),
                     listed_entity=("listed_entity", lambda s: " | ".join(sorted(set(x for x in s if x)))),
                     ticker=("ticker", lambda s: " | ".join(sorted(set(x for x in s if x)))),
                     notes=("notes", lambda s: " | ".join(sorted(set(x for x in s if x)))))
                .reset_index().sort_values(["n_letters_listed", "n_letters"], ascending=False))
    review = out[(out.us_listed_at_letter == "Unclear") | (out.match_confidence == "medium")]

    years = sorted(out["Action Taken Date"].dt.year.unique())
    universe = universe_by_year(years)
    by_year = yearly_comparison(out, universe)
    print(by_year.to_string(index=False))

    counts = out.us_listed_at_letter.value_counts()
    method = pd.DataFrame({"Item": [
        "Question", "US exchange", "Timing", "Subsidiaries", "Linking", "Listing test", "Unclear", "Industry benchmark",
        "Letters", *[f"  {k}" for k in counts.index], "Source data", "Built by"],
        "Detail": [
        "Was the recipient publicly traded on a US exchange on the warning-letter date?",
        "NYSE, Nasdaq, NYSE American/MKT, Cboe. OTC-traded reporting companies count as No.",
        "Status is evaluated on each letter's Action Taken Date; ownership changes are dated.",
        "A recipient owned by a US-listed parent on the letter date is 'Yes - via parent' with the parent's ticker.",
        "All distinct recipient names reviewed by hand; see scripts/19 CURATION for every link and its dates.",
        "Public at the letter date = SEC EDGAR periodic reports around that date (not before IPO, not after acquisition/Form 15). Exchange = documented listing window of the stock (scripts/19 LISTING), dated from its 8-A12B / Form 25 filings where it joined or left an exchange.",
        "Rows the filing record could not settle; also see match_confidence = medium on the 'Needs review' sheet.",
        f"Industry benchmark (sheet 'Sample vs industry by year'): all SEC registrants with EDGAR SIC codes {SIC_TEXT_FULL}, counted in a year if listed on a US exchange at any point that year. Exchange status for firms not hand-checked is rule-based from EDGAR (8-A12B registrations, Form 25 delistings, current listing) - an approximation. EDGAR SIC is the SEC's current code and can differ from Compustat's. 'Sample' = distinct US-listed companies (recipient or its parent) receiving a device warning letter that year; diversified parents (e.g., J&J, Abbott) are in the sample but not in the device-SIC universe.",
        f"{len(out):,} letters / {out['Legal Name'].nunique():,} distinct recipients",
        *[f"{v:,} letters" for v in counts.values],
        "FDA Data Dashboard compliance actions (Devices, Warning Letter); SEC EDGAR submissions API",
        f"scripts/19_warning_letter_us_listing_status.py on {today}"]})

    path = PROCESSED_DIR / f"warning_letters_us_listing_status_{today}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        method.to_excel(xw, sheet_name="Method", index=False)
        by_year.to_excel(xw, sheet_name="Sample vs industry by year", index=False)
        out.to_excel(xw, sheet_name="Letters with listing status", index=False)
        firms.to_excel(xw, sheet_name="Firm summary", index=False)
        review.to_excel(xw, sheet_name="Needs review", index=False)
        universe.sort_values(["year", "company"]).to_excel(
            xw, sheet_name="Device universe firm-years", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    print(counts.to_string())
    print(f"  -> {path.relative_to(REPO_ROOT)}")
    write_summary_workbook(out, universe, today, gv)


if __name__ == "__main__":
    main()
