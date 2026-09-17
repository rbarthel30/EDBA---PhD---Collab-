# 9_17_26_summary

The research question fundamentally asks, "what is the effect of FDA monitoring and action events on 
a.) company's investor-facing disclosure  and b.) capital market response. This question will be tested with three primary outcome variables of interest: 
1.) Disclosure response in earnings calls and SEC filings, proxied by textual indicators for management sentiment, obfuscation, and use of hedging or qualifier language. 
2.) The market response , proxied by abnormal returns and volatility, to the actual product event 
3.) The market response to SEC filings and earnings calls that discuss these events, relative to those that do not.
For the market tests, both short and long time windows will be used to understand the role of these events in signaling longer-run valuation downturns. 

## Descriptives summary - `combined_9_17_26`

The combined dataset holds every 10-K and 10-Q filed by the 117 gvkey-linked medical-device firms: 6,547 filings (1,660 10-Ks and 4,887 10-Qs), with FDA product events and event 8-Ks merged in by firm, year, and reporting quarter. All filings are kept so that quarters with a product event can be compared against quarters without one.

On the event side, the FDA data contain 192 warning letters, 17,448 recalls, and about 10.7 million adverse-event reports at gvkey-linked firms; of these, 96 letters, 7,761 recalls, and about 7.1 million adverse-event reports fall inside a reporting quarter in the panel. That gives 92 filings with a warning letter in the quarter, 1,376 with a recall, and 4,059 with an adverse-event report.

On the disclosure side, 596 filings substantively discuss a warning letter in the MD&A (135 10-Ks, 461 10-Qs), 853 discuss a recall (272 and 581), and 274 discuss an adverse event (108 and 166). Substantive MD&A discussion is more common when the event occurred in the period: 37% of filings with a warning letter in the quarter versus 9% without, 21% versus 11% for recalls, and 5% versus 3% for adverse events. The same pattern holds at the yearly 10-K level (24% versus 8%, 23% versus 12%, and 8% versus 4%). These are raw rates with no controls, and the warning-letter comparison uses only filings from October 2008 onward, when FDA's warning-letter data begins.

There are 176 unique device event 8-Ks (115 warning letter, 62 recall, 6 adverse event); 76 of them merge to a reporting quarter in the panel.

Full tables are in `descriptives_combined_9_17_26.pdf` in this folder.
