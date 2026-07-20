# Panel descriptives - gvkey-year-event (2026-07-19)

## Overall

| Statistic | Value |
|:---|---:|
| Total gvkey-year-event observations | 2,712 |
| Unique firms (gvkey) | 141 |
| Unique gvkey-year cells | 1,915 |
| Year range | 1991-2025 |
| Total underlying events | 7,361,047 |

## By event type

| Event type | Obs (gvkey-year) | Firms | Events | Median/cell |
|:---|---:|---:|---:|---:|
| warning_letter | 98 | 71 | 106 | 1 |
| recall | 768 | 83 | 9,811 | 5 |
| adverse_event | 1,846 | 136 | 7,351,130 | 64 |

## Co-occurrence within a gvkey-year

| Combination | gvkey-years | Share |
|:---|---:|---:|
| warning letter only | 13 | 0.7% |
| recall only | 52 | 2.7% |
| adverse event only | 1,112 | 58.1% |
| letter + recall | 63 | 3.3% |
| letter + adverse event | 81 | 4.2% |
| recall + adverse event | 712 | 37.2% |
| ALL THREE | 59 | 3.1% |

## Firms by event-type coverage

| Firm appears in | Firms |
|:---|---:|
| Warning letters | 71 |
| Recalls | 83 |
| Adverse events | 136 |
| **All three sources** | 58 |

*Sample rule:* an event enters the panel only if its firm resolves to a Compustat gvkey whose ownership window contains the event year.

**Compustat active-firm-year gate (binding).** An event is kept only if its firm has a `comp.funda` annual record for that fiscal year AND market capitalisation is computable (non-missing `prcc_f` and `csho`) - i.e. the firm was publicly traded that year, the precondition for observing any disclosure response. This is the same test Table 1 (script 09) applies, so the panel and Table 1 now share one definition.

> *Note:* the crosswalk ownership-window gate is retained but is near-vacuous on its own - only 2 of 630 name-gvkey pairs carry a real window, the rest defaulting to 1900-2099. The funda gate above is what actually binds.

*Other notes:* warning letters are counted by unique FDA Case/Injunction ID. MAUDE counts include Tier B parent-prefix matches (~44% of reports), split out in `n_mdr_tier_a` / `n_mdr_tier_b`.