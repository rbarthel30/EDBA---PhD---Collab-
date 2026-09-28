# Panel descriptives - gvkey-year-event (2026-09-28)

## Overall

| Statistic | Value |
|:---|---:|
| Total gvkey-year-event observations | 3,049 |
| Unique firms (gvkey) | 172 |
| Unique gvkey-year cells | 2,119 |
| Year range | 1991-2026 |
| Total underlying events | 8,302,496 |

## By event type

| Event type | Obs (gvkey-year) | Firms | Events | Median/cell |
|:---|---:|---:|---:|---:|
| warning_letter | 148 | 88 | 172 | 1 |
| recall | 948 | 101 | 16,322 | 6 |
| adverse_event | 1,953 | 159 | 8,286,002 | 60 |

## Co-occurrence within a gvkey-year

| Combination | gvkey-years | Share |
|:---|---:|---:|
| warning letter only | 19 | 0.9% |
| recall only | 135 | 6.4% |
| adverse event only | 1,129 | 53.3% |
| letter + recall | 106 | 5.0% |
| letter + adverse event | 117 | 5.5% |
| recall + adverse event | 801 | 37.8% |
| ALL THREE | 94 | 4.4% |

## Firms by event-type coverage

| Firm appears in | Firms |
|:---|---:|
| Warning letters | 88 |
| Recalls | 101 |
| Adverse events | 159 |
| **All three sources** | 67 |

*Sample rule:* an event enters the panel only if its firm resolves to a Compustat gvkey whose ownership window contains the event year.

**Compustat active-firm-year gate (binding).** An event is kept only if its firm has a `comp.funda` annual record for that fiscal year AND market capitalisation is computable (non-missing `prcc_f` and `csho`) - i.e. the firm was publicly traded that year, the precondition for observing any disclosure response. This is the same test Table 1 (script 09) applies, so the panel and Table 1 now share one definition.

> *Note:* the crosswalk ownership-window gate binds only where a real window exists - 63 of 568 name-gvkey pairs, chiefly acquired firms re-pointed to the acquirer after the closing year (data/external/project_subsidiary_parent_overrides.csv); the rest default to 1900-2099. The funda gate above is the broad binding test.

*Other notes:* warning letters are counted by unique FDA Case/Injunction ID. MAUDE counts include Tier B parent-prefix matches (~44% of reports), split out in `n_mdr_tier_a` / `n_mdr_tier_b`.