# =============================================================
# Script: 22_device_inspections_vs_warning_letters_chart.py
# Author: Armando Cuello (built with Claude Code)
# Project: FDA Comment Letters & Medtech/Pharma Disclosure (Armando Cuello, EDBA)
# Purpose: One figure answering "what drove the drop in FDA device warning letters
#          after 2015?": FDA kept inspecting and kept finding violations, but turned
#          far fewer of those findings into warning letters.
# Inputs:  data/external/fda_dashboard_device_inspections_by_fy_2026-09-27.csv
#              (FDA Data Dashboard, Inspections; see the README next to it)
#          data/raw/Copy_FDA Warning Letter_Data.xlsx  (FDA Data Dashboard, Compliance
#              Actions: Devices / Warning Letter; counted as distinct letters by case #)
#          FDA CDRH "Medical Device Quality System Data" reports (initial OAI counts,
#              typed in below with their source)
# Outputs: output/figures/device_inspections_vs_warning_letters.png / .pdf
#          output/figures/device_inspections_vs_warning_letters_data.csv
#          output/figures/device_inspections_vs_warning_letters_table.xlsx  (plain-English headers)
# =============================================================
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "figures"
FIRST_FY, LAST_FY = 2009, 2026          # FY2026 is partial: letters through 2026-09-01; classifications lag
PARTIAL_FY = 2026

# Initial OAI classifications (rating at the end of the inspection) of device quality-system
# surveillance inspections, from FDA/CDRH "Medical Device Quality System Data" reports:
#   CY2009-CY2015: total inspections (domestic + foreign) x the reported overall OAI share
#                  (CY2008-2015 chart in the CY2015 report) -> approximate;
#   CY2016 (104 + 86) and FY2017 (146 + 70): counts reported directly.
QS_INSPECTIONS = {2009: 1509 + 228, 2010: 1792 + 271, 2011: 1931 + 341, 2012: 1859 + 393,
                  2013: 1741 + 460, 2014: 1619 + 594, 2015: 1484 + 620}
QS_OAI_SHARE = {2009: .07, 2010: .07, 2011: .07, 2012: .08, 2013: .08, 2014: .09, 2015: .11}
INITIAL_OAI = {y: round(QS_INSPECTIONS[y] * QS_OAI_SHARE[y]) for y in QS_INSPECTIONS}
INITIAL_OAI.update({2016: 104 + 86, 2017: 146 + 70})

# FDA device-quality program and organizational milestones: (date, short label).
# Plotted at their position within the federal fiscal year (FY starts Oct 1).
MILESTONES = [
    ("2011-10-31", "Case for Quality launched (CDRH quality report), Oct 2011"),
    ("2017-05-15", "ORA inspectorate realigned into device-specialized program, May 2017"),
    ("2018-01-02", "Case for Quality voluntary pilot program begins, Jan 2018"),
    ("2019-03-18", "CDRH 'super office' (OPEQ) reorganization begins, Mar 2019"),
    ("2020-03-10", "COVID: routine surveillance inspections paused, Mar 2020"),
    ("2023-09-14", "Voluntary Improvement Program final guidance, Sep 2023"),
]


def fy_position(date):
    """Continuous x-position: FY n spans (n-0.5, n+0.5); Oct 1 = start of the next FY."""
    d = pd.Timestamp(date)
    fy = d.year + (d.month >= 10)
    start = pd.Timestamp(f"{fy - 1}-10-01")
    return fy - 0.5 + (d - start).days / 365.25

# Palette: reference categorical slots 1-3 (validated all-pairs, light mode)
C_INSP, C_WL, C_FIND = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"


def load():
    ins = pd.read_csv(ROOT / "data/external/fda_dashboard_device_inspections_by_fy_2026-09-27.csv")
    wl = pd.read_excel(ROOT / "data/raw/Copy_FDA Warning Letter_Data.xlsx",
                       sheet_name="Extracted Data from FDA Website").drop_duplicates("Case/Injunction ID")
    d = wl["Action Taken Date"]
    wl["fiscal_year"] = d.dt.year + (d.dt.month >= 10)      # federal FY starts Oct 1
    letters = wl.groupby("fiscal_year").size().rename("warning_letters")
    df = ins.merge(letters, on="fiscal_year", how="left")
    df = df[(df.fiscal_year >= FIRST_FY) & (df.fiscal_year <= LAST_FY)].copy()
    df["letters_per_100_inspections_with_findings"] = 100 * df.warning_letters / df.inspections_with_483_citations
    df["initial_oai_fda_reports"] = df.fiscal_year.map(INITIAL_OAI)
    return df


def line_with_partial(ax, x, y, color, **kw):
    """Solid line for complete years; dotted segment and hollow marker for the partial final year."""
    full = x < PARTIAL_FY
    ax.plot(x[full], y[full], color=color, **kw)
    ax.plot(x[-2:] if len(x) > 1 else x, y[-2:] if len(y) > 1 else y, color=color,
            lw=kw.get("lw", 2), linestyle=(0, (2, 2)))
    ax.plot(x[~full], y[~full], color=color, lw=0, marker=kw.get("marker", "o"),
            ms=kw.get("ms", 4) + 1, markerfacecolor=SURF, markeredgewidth=1.5)


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axvspan(2019.5, 2021.5, color="#f1f0ec", zorder=0)        # COVID inspection pause
    ax.axvline(2015.5, color=INK2, linewidth=1, linestyle=(0, (3, 3)), zorder=1)


def main():
    df = load()
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "device_inspections_vs_warning_letters_data.csv", index=False)
    table = df.rename(columns={
        "fiscal_year": "Fiscal year (Oct-Sep)",
        "device_inspections": "Device inspections",
        "inspections_with_483_citations": "Inspections that found violations (Form 483)",
        "compliance_inspections": "Quality-system (compliance) inspections",
        "initial_oai_fda_reports": "OAI when inspection ended (FDA reports, to FY2017)",
        "compliance_oai_final": "OAI after FDA final review (same inspections)",
        "warning_letters": "Warning letters issued (devices)",
        "letters_per_100_inspections_with_findings": "Letters per 100 inspections that found violations",
    })[["Fiscal year (Oct-Sep)", "Device inspections", "Inspections that found violations (Form 483)",
        "Quality-system (compliance) inspections", "OAI when inspection ended (FDA reports, to FY2017)",
        "OAI after FDA final review (same inspections)", "Warning letters issued (devices)",
        "Letters per 100 inspections that found violations"]].round(1)
    table["Fiscal year (Oct-Sep)"] = table["Fiscal year (Oct-Sep)"].astype(str).replace({"2026": "2026 (partial)"})
    table.to_excel(OUT / "device_inspections_vs_warning_letters_table.xlsx", index=False)
    x = df.fiscal_year

    fig, allax = plt.subplots(5, 1, figsize=(10, 18.2), sharex=True,
                              gridspec_kw={"height_ratios": [0.7, 1.1, 1, 0.85, 0.85], "hspace": 0.45})
    fig.patch.set_facecolor(SURF)
    axes = allax[1:]

    # --- timeline strip: FDA program / organizational milestones ---
    t = allax[0]
    t.set_facecolor(SURF)
    for sp in t.spines.values():
        sp.set_visible(False)
    t.set_yticks([]); t.tick_params(length=0)
    t.set_ylim(0, 1)
    t.axhline(0.12, color=GRID, lw=1.5)
    t.axvspan(2019.5, 2021.5, color="#f1f0ec", zorder=0)
    t.axvline(2015.5, ymax=0.3, color=INK2, linewidth=1, linestyle=(0, (3, 3)))
    for i, (date, label) in enumerate(MILESTONES, start=1):
        xp = fy_position(date)
        t.plot([xp, xp], [0.12, 0.30], color=INK, lw=1)
        t.plot(xp, 0.12, marker="o", ms=6, color=INK)
        t.text(xp, 0.33, str(i), fontsize=9, fontweight="bold", color=INK, ha="center", va="bottom")
        t.text(2008.6, 0.98 - (i - 1) * 0.105, f"{i}  {label}", fontsize=7.9, color=INK, va="top", ha="left")
        for ax in axes:
            ax.axvline(xp, color=INK2, lw=0.8, alpha=0.35, zorder=1)
        axes[0].text(xp, 2850, str(i), fontsize=7.5, color=INK2, ha="center", va="top")
    t.set_title("FDA device-quality program and organizational milestones",
                loc="left", fontsize=12, fontweight="bold", color=INK, pad=8)

    # --- A. inspections and inspections that found violations (counts) ---
    a = axes[0]; style(a)
    line_with_partial(a, x.values, df.device_inspections.values, C_INSP, lw=2, marker="o", ms=4)
    line_with_partial(a, x.values, df.inspections_with_483_citations.values, C_FIND, lw=2, marker="o", ms=4)
    last = df.iloc[-1]
    a.annotate("Device inspections", (x.iloc[-1], last.device_inspections), xytext=(8, 0),
               textcoords="offset points", va="center", fontsize=9, color=INK)
    a.annotate("Inspections that found\nviolations (Form 483 issued)",
               (x.iloc[-1], last.inspections_with_483_citations), xytext=(8, 0),
               textcoords="offset points", va="center", fontsize=9, color=INK)
    a.set_title("A.  FDA kept inspecting device firms, and kept finding violations",
                loc="left", fontsize=12, fontweight="bold", color=INK, pad=10)
    a.set_ylabel("Inspections per fiscal year", color=INK2, fontsize=9)
    a.set_ylim(0, 2900)

    # --- B. serious findings: OAI at the end of the inspection vs. as finalized (same inspection type) ---
    b = axes[1]; style(b)
    oai = df.dropna(subset=["initial_oai_fda_reports"])
    b.plot(oai.fiscal_year, oai.initial_oai_fda_reports, color=INK, lw=2, marker="D", ms=6, zorder=3)
    b.plot(x, df.compliance_oai_final, color=INK2, lw=2, linestyle=(0, (5, 2.5)), marker="o", ms=5,
           markerfacecolor=SURF, markeredgecolor=INK2, markeredgewidth=1.5, zorder=2)
    for fy, v in zip(oai.fiscal_year, oai.initial_oai_fda_reports):
        if fy in (2015, 2016, 2017):
            b.annotate(f"{int(v)}", (fy, v), xytext=(0, 8), textcoords="offset points",
                       ha="center", fontsize=8.5, color=INK)
    for fy, off, ha in ((2015, (0, 16), "center"), (2016, (0, -9), "center"), (2017, (0, -9), "center")):
        v = int(df.loc[df.fiscal_year == fy, "compliance_oai_final"].iloc[0])
        b.annotate(f"{v}", (fy, v), xytext=off, textcoords="offset points",
                   ha=ha, va="top", fontsize=8.5, color=INK2)
    b.annotate("Rated OAI when the\ninspection ended, solid\n(FDA reports; published\nonly through FY2017)",
               (2017, 216), xytext=(10, 0), textcoords="offset points", va="center", fontsize=8.5, color=INK)
    b.annotate("Rated OAI after FDA's\nfinal review, dashed\n(FDA Data Dashboard)",
               (x.iloc[-1], df.compliance_oai_final.iloc[-1]), xytext=(8, 0), textcoords="offset points",
               va="center", fontsize=8.5, color=INK)
    b.set_title("B.  Serious violations (OAI) kept being found, but most were no longer finalized as OAI",
                loc="left", fontsize=12, fontweight="bold", color=INK, pad=10)
    b.set_ylabel("Quality-system inspections\nrated OAI", color=INK2, fontsize=9)
    b.set_ylim(0, 270)

    # --- C. warning letters ---
    w = axes[2]; style(w)
    full = x < PARTIAL_FY
    w.bar(x[full], df.warning_letters[full], color=C_WL, width=0.62, zorder=2)
    w.bar(x[~full], df.warning_letters[~full], color=SURF, edgecolor=C_WL, hatch="////", linewidth=1.2,
          width=0.62, zorder=2)
    for fy, v in zip(x, df.warning_letters):
        if fy in (2013, 2015, 2016, 2017, 2025, 2026):
            w.annotate(f"{int(v)}", (fy, v), xytext=(0, 3), textcoords="offset points",
                       ha="center", va="bottom", fontsize=8.5, color=INK2)
    w.set_title("C.  And far fewer warning letters were issued",
                loc="left", fontsize=12, fontweight="bold", color=INK, pad=10)
    w.set_ylabel("Warning letters (devices)", color=INK2, fontsize=9)
    w.set_ylim(0, 250)

    # --- D. escalation rate ---
    c = axes[3]; style(c)
    line_with_partial(c, x.values, df.letters_per_100_inspections_with_findings.values, C_WL, lw=2, marker="o", ms=4)
    for fy in (2015, 2017, 2021, 2025):
        v = df.loc[df.fiscal_year == fy, "letters_per_100_inspections_with_findings"].iloc[0]
        c.annotate(f"{v:.0f}", (fy, v), xytext=(0, 8), textcoords="offset points",
                   ha="center", fontsize=8.5, color=INK)
    c.set_title("D.  Warning letters per 100 inspections that found violations",
                loc="left", fontsize=12, fontweight="bold", color=INK, pad=10)
    c.set_ylabel("Letters per 100 inspections", color=INK2, fontsize=9)
    c.set_ylim(0, 36)
    c.set_xticks(list(x))
    c.set_xticklabels([f"'{str(v)[2:]}" + ("*" if v == PARTIAL_FY else "") for v in x])
    c.set_xlabel("Federal fiscal year (October-September)", color=INK2, fontsize=9)

    axes[0].text(2015.55, 2700, "FY2016:\nletters drop", fontsize=8.5, color=INK2, va="top")

    fig.suptitle("From FY2015 to FY2017, FDA device inspections dipped about 10%,\n"
                 "but device warning letters fell 74% (167 to 44)",
                 x=0.1, y=0.988, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.text(0.1, 0.006,
             "Sources: FDA Data Dashboard (datadashboard.fda.gov), Inspections and Compliance Actions, product type Devices,\n"
             "accessed Sept 2026; warning letters counted once per FDA case number (all 1,760 letters, FY2009-FY2026).\n"
             "*FY2026 is partial (letters through Sept 1, 2026; inspection classifications still being finalized): hatched / hollow.\n"
             "Panel B: both lines count the same type of inspection, device quality-system (compliance) inspections. Solid: rated\n"
             "'Official Action Indicated' when the inspection ended, from FDA/CDRH Medical Device Quality System Data reports\n"
             "(CY2009-2015 = inspections x reported OAI share, approximate; CY2016 and FY2017 reported counts; FDA stopped\n"
             "publishing after FY2017). Dashed: the same inspections' rating after FDA's final review (dashboard project area\n"
             "'Compliance: Devices'; FY2015: 2,132 inspections vs 2,104 in FDA's report). The two agree through FY2015, then split.\n"
             "Some letters are not inspection-based (e.g., marketing violations), so panel D is an upper bound; FY2020-21 = COVID.\n"
             "Milestones: FDA Case for Quality page and 'Understanding Barriers to Medical Device Quality' (Oct 31, 2011); ORA\n"
             "Program Alignment (May 15, 2017); Federal Register 2017-28044 (pilot Jan 2, 2018 - Dec 28, 2018); CDRH OPEQ\n"
             "reorganization (from March 2019); FDA inspection pause (March 2020); VIP final guidance (Sept 14, 2023).",
             fontsize=7.6, color=INK2, va="bottom", linespacing=1.45)
    fig.subplots_adjust(left=0.1, right=0.8, top=0.935, bottom=0.13)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"device_inspections_vs_warning_letters.{ext}", dpi=200, facecolor=SURF)
    print(df[["fiscal_year", "device_inspections", "inspections_with_483_citations", "warning_letters",
              "letters_per_100_inspections_with_findings", "oai_final", "initial_oai_fda_reports"]]
          .round(1).to_string(index=False))


if __name__ == "__main__":
    main()
