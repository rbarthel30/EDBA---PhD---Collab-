# 9_17_26_summary

The research question fundamentally asks, "what is the effect of FDA monitoring and action events on 
a.) company's investor-facing disclosure  and b.) capital market response. This question will be tested with three primary outcome variables of interest: 
1.) Disclosure response in earnings calls and SEC filings, proxied by textual indicators for management sentiment, obfuscation, and use of hedging or qualifier language. 
2.) The market response , proxied by abnormal returns and volatility, to the actual product event 
3.) The market response to SEC filings and earnings calls that discuss these events, relative to those that do not 
For the market tests, both short and long time windows will be used to understand the role of these events in signaling longer-run valuation downturns. 

## Descriptives summary - `combined_9_17_26`

Full tables: `descriptives_combined_9_17_26.pdf` (this folder) / `output/tables/descriptives_combined_9_17_26.md`. Dataset: `data/combined_9_17_26.csv`.

**The dataset.** Every 10-K and 10-Q filed by the gvkey-linked medical-device firms - 6,547 filings (1,660 10-Ks, 4,887 10-Qs), 117 firms, reporting periods ending 2004-2026. One row per filing = one firm reporting quarter. FDA product events and event 8-Ks are merged in by firm x year x reporting quarter, each placed in the reporting period its own date falls in. All filings are kept, so quarters with a product event can be compared against quarters without one.

**Product events (the event dates themselves, from FDA data).**

| Event | All gvkey-linked firms | At the 117 panel firms | Merged to a reporting quarter | Filings (quarters) with the event |
|:---|---:|---:|---:|---:|
| Warning letters | 192 | 128 | 96 | 92 |
| Recalls (Part 806) | 17,448 | 11,722 | 7,761 | 1,376 |
| Adverse-event reports (Part 803) | 10,737,528 | 9,588,496 | 7,114,479 | 4,059 |

Events that do not merge fall before a firm's first filing in the panel (it starts in 2005), after its last, or at firms outside the panel. 2,367 filings have no product event of any type in the quarter.

**Filings with a substantive mention of the event in the MD&A** (tied to an actual event, not hedged risk-factor boilerplate).

| Event | 10-K | 10-Q | Total |
|:---|---:|---:|---:|
| Warning letter | 135 | 461 | 596 |
| Recall | 272 | 581 | 853 |
| Adverse event | 108 | 166 | 274 |
| Any of the three (each filing once) | 367 | 891 | 1,258 |

**Substantive MD&A disclosure rate, with vs without the event** (raw rates, no controls).

| Event | Quarterly: event in quarter | Quarterly: no event | Yearly (10-K): event in fiscal year | Yearly (10-K): no event |
|:---|---:|---:|---:|---:|
| Warning letter* | 37.4% (34 of 91) | 9.2% (473 of 5,117) | 24.4% (21 of 86) | 7.9% (93 of 1,184) |
| Recall | 21.1% (291 of 1,376) | 10.9% (562 of 5,171) | 23.0% (144 of 626) | 12.4% (128 of 1,034) |
| Adverse event | 4.9% (199 of 4,059) | 3.0% (75 of 2,488) | 7.7% (90 of 1,166) | 3.6% (18 of 494) |

\* Warning-letter rows use only filings from October 2008 onward, when FDA's warning-letter data begins; before that, letters are unobserved rather than absent. Disclosure in a "no event" period is largely continued discussion of an earlier period's event, since an event is attached only to the period it is dated in.

**Event 8-Ks.** 176 unique device 8-Ks (222 documents counting exhibits): 115 warning letter, 62 recall, 6 adverse event. 80 were filed by firms in the 10-K/10-Q panel, and 76 merge to a reporting quarter (62 warning letter, 15 recall, 5 adverse event), covering 74 filings.
