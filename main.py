# polymarket-faa-attribution-02 entry (Python 3.13, standard library only).
#
# Forecast: for each market, five quantiles of the Yes price at every minute of
# the 240 minutes after the checkpoint, from that market's own price history
# alone (the run is offline; the case file is everything it knows).
#
# Model — adaptive persistence, per market:
#   * centre: the last price, plus a small pull toward the market's last-12h
#     mean that grows with horizon (probability prices mean-revert). No
#     drift: an hourly drift estimated from history hurt on every practice
#     case — these prices move in steps and jump between regimes, and the
#     drift estimate mostly replays the last regime jump.
#   * spread: a per-market one-minute volatility, the RMS of one-minute moves
#     over the last hour blended with the last 12h, winsorized at 0.025 so a
#     rare 0.4 jump cannot set the scale, clipped to a floor and a cap. The
#     band grows like h ** 0.4, slower than a random walk's sqrt(h), and is
#     scaled by 0.7: the typical minute is flat or a small tick, so a band
#     wide enough to cover the rare jumps costs more, in pinball loss, than
#     the jumps themselves. Normal outer quantiles, not heavier tails, for
#     the same reason.
#   * everything is clamped to [0, 1] and rounded to 6 decimals; the program
#     is pure arithmetic on the input, so two runs give byte-identical output.
#
# The house baseline is this shape with a fixed sigma of 0.0025, sqrt(h)
# growth, scale 1 and no mean reversion; every parameter here is estimated
# from the case's own history, never from the future. On the six practice
# cases (NVIDIA event) this scores a mean pinball loss of 0.2705 against the
# baseline's 0.3636, better on every case — but the practice is a different
# event, so the parameters are kept moderate and generic rather than tuned
# to the last decimal.

import json
import math
import os
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at the five levels.
Z_NORMAL = [-1.644854, -0.674490, 0.0, 0.674490, 1.644854]
# Student-t with 5 degrees of freedom at the five levels (heavier tails).
Z_T5 = [-2.015048, -0.726687, 0.0, 0.726687, 2.015048]

# Tunable constants (chosen on the practice cases; see README).
SIGMA_FLOOR = 0.0008   # per sqrt-minute; never forecast a dead-quiet market
SIGMA_CAP = 0.012      # per sqrt-minute; a jumpy market stays jumpy, not absurd
DRIFT_CAP = 0.0        # drift DISABLED: hourly drift from history hurt on every
                       # practice case (regime jumps dominate it); centre stays
                       # at the last price
DRIFT_SHRINK_K = 4.0   # drift shrink: n / (n + K) over the hourly changes seen
MOMENTUM_W = 0.0       # weight on the last 60-minute move (0 = off; also hurt)
MEANREV_W = 0.10       # pull toward the 12h mean, growing with horizon
MEANREV_TAU = 600.0    # minutes; pull grows as 1 - exp(-h / TAU)
USE_T_TAILS = False    # normal outer quantiles: heavier t(5) tails cost more
                       # than they save on practice
SPREAD_SCALE = 0.7     # multiplier on the whole band width
SPREAD_ALPHA = 0.4     # band grows as h ** ALPHA (0.5 = random walk; 0.4 fits
                       # steppy prices: long-horizon moves stop growing)
WINSOR_CAP = 0.025     # cap |1-min move| before RMS: rare 0.4 jumps must not
                       # set sigma (0 = off)
VOL_SHORT_MIN = 60     # minutes for the recent volatility window
VOL_LONG_MIN = 720     # minutes for the longer volatility window


def price6(x: float) -> float:
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)) * 1e6) / 1e6 + 0.0


def _rms(values) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / len(values))


def forecast_market(prices, horizon: int):
    """240 rows x 5 quantiles for one market, from its minute prices."""
    n = len(prices)
    if n == 0:
        x = 0.5
        return [[price6(x)] * 5 for _ in range(horizon)]
    x = float(prices[-1])

    # --- one-minute volatility: RMS of moves, recent blended with longer ---
    # Moves are winsorized first: one 0.4 jump in the window must not set the
    # scale — the typical minute is flat or a small tick, and the bands are
    # scored on the typical minute far more often than on the rare jump.
    diffs = [prices[i + 1] - prices[i] for i in range(n - 1)]
    if WINSOR_CAP:
        diffs = [max(-WINSOR_CAP, min(WINSOR_CAP, d)) for d in diffs]
    if diffs:
        short = diffs[-VOL_SHORT_MIN:]
        long_ = diffs[-VOL_LONG_MIN:]
        sigma1 = math.sqrt(0.5 * _rms(short) ** 2 + 0.5 * _rms(long_) ** 2)
    else:
        sigma1 = 0.0025
    sigma1 = min(SIGMA_CAP, max(SIGMA_FLOOR, sigma1))

    # --- drift: mean hourly change over the last 24h, shrunk and capped ---
    hourly = []
    # non-overlapping 60-minute changes, most recent first, up to 24 of them
    for k in range(24):
        hi = n - 1 - 60 * k
        lo = hi - 60
        if lo < 0:
            break
        hourly.append(prices[hi] - prices[lo])
    if hourly:
        drift = sum(hourly) / len(hourly) * (len(hourly) / (len(hourly) + DRIFT_SHRINK_K))
        drift = max(-DRIFT_CAP, min(DRIFT_CAP, drift))
    else:
        drift = 0.0
    if MOMENTUM_W and n > 61:
        drift += MOMENTUM_W * (prices[-1] - prices[-61])
        drift = max(-DRIFT_CAP, min(DRIFT_CAP, drift))

    # --- mean reversion target: the market's last-12h mean price ---
    recent = prices[-VOL_LONG_MIN:]
    mean24 = sum(recent) / len(recent) if recent else x

    z = Z_T5 if USE_T_TAILS else Z_NORMAL
    rows = []
    for h in range(1, horizon + 1):
        centre = x + drift * h / 60.0
        if MEANREV_W:
            centre += MEANREV_W * (mean24 - x) * (1.0 - math.exp(-h / MEANREV_TAU))
        spread = SPREAD_SCALE * sigma1 * (h ** SPREAD_ALPHA)
        row = [price6(centre + zj * spread) for zj in z]
        # rounding/clamping is monotone, but enforce non-decreasing anyway
        for j in range(1, 5):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        rows.append(row)
    return rows


def main() -> None:
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = sorted(p for p in in_dir.iterdir() if p.name.endswith(".in"))
    for path in inputs:
        case = json.loads(path.read_text(encoding="utf-8"))
        horizon = int(case["horizon_minutes"])
        quantiles = case.get("quantiles", QUANTILES)
        if list(quantiles) != QUANTILES:
            raise ValueError(f"{path.name} asks for quantiles {quantiles}")
        forecasts = [
            {"id": m["id"], "q": forecast_market(m["prices"], horizon)}
            for m in case["markets"]
        ]
        out_path = out_dir / f"{path.name[:-3]}.out"
        out_path.write_text(json.dumps({"forecasts": forecasts}) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
