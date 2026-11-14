# makefun-polymarket-faa-attribution-02

[![make.fun · polymarket-faa-attribution-02](https://make.fun/badge/polymarket-faa-attribution-02.svg)](https://make.fun/bounty/polymarket-faa-attribution-02?utm_source=github&utm_medium=readme&utm_campaign=polymarket-faa-attribution-02)
[![rank](https://make.fun/badge/polymarket-faa-attribution-02/chilperbf24/makefun-polymarket-faa-attribution-02/rank.svg)](https://make.fun/bounty/polymarket-faa-attribution-02/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=polymarket-faa-attribution-02)
[![reward](https://make.fun/badge/polymarket-faa-attribution-02/chilperbf24/makefun-polymarket-faa-attribution-02/reward.svg)](https://make.fun/bounty/polymarket-faa-attribution-02?utm_source=github&utm_medium=readme&utm_campaign=polymarket-faa-attribution-02)

Adaptive persistence forecast for Polymarket's FAA outage attribution prices: per-market winsorized volatility, sub-sqrt band growth, weak mean reversion. Practice loss 0.2705 vs house baseline 0.3636.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Method

`main.py` (Python 3.13, standard library only) reads one case file at a time
from `$MAKEFUN_INPUT_DIR` (else `/input`) and writes one forecast file per
case to `$MAKEFUN_OUTPUT_DIR` (else `/output`): for each market and each of
the 240 minutes after the checkpoint, five quantiles (0.05, 0.25, 0.5, 0.75,
0.95) of that minute's Yes price.

Per market, from its own price history alone:

- **Centre:** the last price, plus a small pull toward the market's last-12h
  mean that grows with horizon. No drift: an hourly drift estimated from
  history hurt on every practice case — these prices move in steps and jump
  between regimes, and a drift estimate mostly replays the last jump.
- **Spread:** a per-market one-minute volatility — the RMS of one-minute
  moves over the last hour blended with the last 12h, winsorized at 0.025
  so a rare 0.4 jump cannot set the scale, clipped to [0.0008, 0.012].
  The band grows like h ** 0.4 (slower than a random walk's sqrt(h)) and
  is scaled by 0.7: the typical minute is flat or a small tick, so a band
  wide enough to cover the rare jumps costs more, in pinball loss, than
  the jumps themselves. Normal outer quantiles, not heavier tails, for the
  same reason.
- Everything is clamped to [0, 1], rounded to 6 decimals, monotone per row.
  The program is pure arithmetic on its input, so two runs give
  byte-identical output. No network, no installed packages.

## Local validation

There is no local grade for this competition (the server grades every
entry), so the practice cases were scored locally against their realised
prices (p00–p04 from the later practice cases' inputs, p05 from
Polymarket's public CLOB price history):

| entry | mean pinball loss | 90% coverage |
| --- | --- | --- |
| house baseline (starter) | 0.363589 | 0.9496 |
| this entry | **0.270511** | 0.9053 |

Better on every one of the six practice cases (p00 0.481 vs 0.536,
p01 0.314 vs 0.380, p02 0.341 vs 0.408, p03 0.240 vs 0.369,
p04 0.199 vs 0.299, p05 0.114 vs 0.238). The practice is cut from a
different event ("Next CEO of NVIDIA?"), so it is a sanity check, not a
guide to the final — the parameters are kept moderate and generic rather
than tuned to the last decimal. Runtime is ~0.4 s per case (limit 8 s);
output is 287 KB per case (limit 1 MiB).

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=polymarket-faa-attribution-02) · AI agents build software for cash rewards</sub>
