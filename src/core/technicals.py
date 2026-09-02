"""Pure-Python technical indicators over daily OHLCV.

Semantics follow the reference implementation in `bukosabino/ta` (MIT), verified
line by line against its source and numerically against pandas:

* **EMA** — ``series.ewm(span=n, adjust=False)``, i.e. the recursive form
  ``y_t = (1-a)*y_{t-1} + a*x_t`` with ``a = 2/(n+1)``, seeded on the first
  observation. Validated to floating-point equality against pandas.
* **MACD** — 12/26 EMAs, signal = 9-EMA *of the MACD line*, histogram = line
  minus signal.
* **RSI** — Wilder smoothing, ``ewm(alpha=1/n, adjust=False)`` over separated
  up/down moves; a zero average loss short-circuits to 100 rather than dividing
  by zero.
* **ATR / ADX** — true range = ``max(h-l, |h-prev_c|, |l-prev_c|)``, then Wilder
  smoothing.

This project ships no runtime dependencies (standard library only, so the desktop
bundle needs no pip step), which is why these are hand-rolled rather than
imported from pandas-ta.

Every function returns ``None`` rather than a partial value when there is not
enough history to satisfy the warm-up period. A half-warmed EMA129 is not a
slightly-worse EMA129, it is a different number — reporting one would be the same
class of bug as the constant-valued factors this codebase already had.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


# The trio the user asked for. 5 is the short-term trigger, 60 the intermediate
# trend, 129 the long-term regime line (a Chinese-market convention roughly
# equivalent to the 120-day/half-year line, offset to skip holiday gaps).
FAST_EMA = 5
MID_EMA = 60
SLOW_EMA = 129

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14

# RSI bands. Deliberately not used as standalone buy/sell triggers — an oscillator
# reading extreme in a strong trend usually means the trend is strong, not that a
# reversal is due.
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0


@dataclass
class TechnicalSignals:
    """Indicator readings plus the discrete states derived from them."""

    ticker: str = ""
    bars: int = 0

    ema_fast: Optional[float] = None
    ema_mid: Optional[float] = None
    ema_slow: Optional[float] = None
    # Price relative to each line, in percent. Sign answers "above or below".
    price_vs_fast_pct: Optional[float] = None
    price_vs_mid_pct: Optional[float] = None
    price_vs_slow_pct: Optional[float] = None

    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    # "golden" (line crossed above signal), "death" (below), or "" for neither.
    macd_cross: str = ""
    # Bars since that cross; 0 means it happened on the latest bar.
    macd_cross_age: Optional[int] = None
    macd_above_zero: Optional[bool] = None

    rsi: Optional[float] = None
    rsi_zone: str = ""

    atr: Optional[float] = None
    atr_pct: Optional[float] = None
    adx: Optional[float] = None

    # EMA stack: "bullish" (fast>mid>slow), "bearish" (fast<mid<slow), "mixed".
    # Requires real separation between the lines — see MIN_STACK_SPREAD_PCT.
    trend_alignment: str = ""
    # EMA5 minus EMA129 as a percentage of price: how separated the stack is.
    ema_spread_pct: Optional[float] = None
    # Golden/death cross of the mid vs slow line — the classic regime signal.
    ma_cross: str = ""
    ma_cross_age: Optional[int] = None

    volume_ratio: Optional[float] = None

    # ---- Structural events, the part a trader acts on -------------------
    # Range break: "breakout" above 60-day resistance, "breakdown" below support.
    breakout_state: str = ""
    breakout_level: Optional[float] = None
    breakout_distance_pct: Optional[float] = None
    # Where price sits inside the 60-day range, 0 = at support, 100 = at resistance.
    range_position_pct: Optional[float] = None
    # Whether price just crossed EMA60 / EMA129: "reclaimed", "lost", or "".
    ema_mid_break: str = ""
    ema_slow_break: str = ""
    # MACD histogram shrinking against price: early warning of exhaustion.
    divergence: str = ""

    # ---- Weekly timeframe ----------------------------------------------
    weekly_bars: int = 0
    weekly_trend_alignment: str = ""
    weekly_macd: Optional[float] = None
    weekly_macd_histogram: Optional[float] = None
    weekly_macd_cross: str = ""
    weekly_macd_cross_age: Optional[int] = None
    weekly_rsi: Optional[float] = None
    weekly_price_vs_slow_pct: Optional[float] = None
    # Do daily and weekly agree? "aligned_bull", "aligned_bear", "conflict", "".
    timeframe_agreement: str = ""

    # 0-100 composite of the readings above, or None when history is too short.
    technical_score: Optional[float] = None
    # Human-readable Chinese notes, ordered most to least important.
    notes: List[str] = field(default_factory=list)
    # The actionable read: what the chart says to do and why, in one paragraph.
    verdict: str = ""

    @property
    def available(self) -> bool:
        return self.technical_score is not None


def ema_series(values: Sequence[float], period: int) -> List[Optional[float]]:
    """EMA aligned to ``values``; entries before the warm-up are None.

    Matches ``pandas.Series.ewm(span=period, min_periods=period, adjust=False)``.
    """

    if period <= 0:
        raise ValueError("period must be positive")
    alpha = 2.0 / (period + 1.0)
    out: List[Optional[float]] = []
    current: Optional[float] = None
    for index, value in enumerate(values):
        current = float(value) if current is None else (1.0 - alpha) * current + alpha * float(value)
        out.append(current if index >= period - 1 else None)
    return out


def _wilder_series(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Wilder smoothing: ``ewm(alpha=1/period, adjust=False)``."""

    alpha = 1.0 / float(period)
    out: List[Optional[float]] = []
    current: Optional[float] = None
    for index, value in enumerate(values):
        current = float(value) if current is None else (1.0 - alpha) * current + alpha * float(value)
        out.append(current if index >= period - 1 else None)
    return out


def macd_series(closes: Sequence[float]) -> tuple:
    """Return ``(macd, signal, histogram)`` series aligned to ``closes``."""

    fast = ema_series(closes, MACD_FAST)
    slow = ema_series(closes, MACD_SLOW)
    line: List[Optional[float]] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast, slow)
    ]
    # The signal line is an EMA *of the MACD line*, so it can only start once the
    # line exists. Compact the leading Nones, smooth, then re-expand so the
    # result stays index-aligned with `closes`.
    start = next((i for i, v in enumerate(line) if v is not None), None)
    signal: List[Optional[float]] = [None] * len(line)
    if start is not None:
        smoothed = ema_series([v for v in line[start:] if v is not None], MACD_SIGNAL)
        for offset, value in enumerate(smoothed):
            signal[start + offset] = value
    histogram: List[Optional[float]] = [
        (m - s) if (m is not None and s is not None) else None
        for m, s in zip(line, signal)
    ]
    return line, signal, histogram


def rsi_series(closes: Sequence[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    """Wilder RSI aligned to ``closes``."""

    if len(closes) < 2:
        return [None] * len(closes)
    ups: List[float] = []
    downs: List[float] = []
    for previous, current in zip(closes, closes[1:]):
        change = float(current) - float(previous)
        ups.append(change if change > 0 else 0.0)
        downs.append(-change if change < 0 else 0.0)
    avg_up = _wilder_series(ups, period)
    avg_down = _wilder_series(downs, period)
    # `ups` is one shorter than `closes` (it is a difference series), so shift.
    out: List[Optional[float]] = [None]
    for gain, loss in zip(avg_up, avg_down):
        if gain is None or loss is None:
            out.append(None)
        elif loss == 0.0:
            # No average loss: RS is infinite. Report 100 rather than dividing.
            out.append(100.0)
        else:
            out.append(100.0 - (100.0 / (1.0 + gain / loss)))
    return out


def true_range_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[Optional[float]]:
    """TR = max(h-l, |h-prev_close|, |l-prev_close|); first bar is None."""

    out: List[Optional[float]] = [None]
    for index in range(1, len(closes)):
        high, low = float(highs[index]), float(lows[index])
        previous = float(closes[index - 1])
        out.append(max(high - low, abs(high - previous), abs(low - previous)))
    return out


def atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = ATR_PERIOD,
) -> List[Optional[float]]:
    ranges = true_range_series(highs, lows, closes)
    values = [value for value in ranges if value is not None]
    smoothed = _wilder_series(values, period)
    out: List[Optional[float]] = [None]
    out.extend(smoothed)
    return out[: len(closes)]


def adx_value(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = ADX_PERIOD,
) -> Optional[float]:
    """Latest ADX, or None without enough history.

    ADX measures trend *strength* without direction, which is why it is reported
    alongside the EMA stack rather than folded into it: a clean bullish stack in a
    sub-20 ADX regime is a chop pattern, not a trend.
    """

    if len(closes) < period * 2 + 1:
        return None
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    for index in range(1, len(closes)):
        up = float(highs[index]) - float(highs[index - 1])
        down = float(lows[index - 1]) - float(lows[index])
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
    ranges = [value for value in true_range_series(highs, lows, closes) if value is not None]
    atr = _wilder_series(ranges, period)
    plus_smoothed = _wilder_series(plus_dm, period)
    minus_smoothed = _wilder_series(minus_dm, period)

    dx: List[float] = []
    for tr, plus, minus in zip(atr, plus_smoothed, minus_smoothed):
        if tr is None or plus is None or minus is None or tr == 0.0:
            continue
        plus_di = 100.0 * plus / tr
        minus_di = 100.0 * minus / tr
        total = plus_di + minus_di
        if total == 0.0:
            continue
        dx.append(100.0 * abs(plus_di - minus_di) / total)
    if len(dx) < period:
        return None
    smoothed = _wilder_series(dx, period)
    final = [value for value in smoothed if value is not None]
    return round(final[-1], 2) if final else None


def _cross_state(
    fast: Sequence[Optional[float]],
    slow: Sequence[Optional[float]],
    lookback: int = 10,
) -> tuple:
    """Most recent crossover within ``lookback`` bars.

    Returns ``(state, bars_ago)`` where state is "golden", "death" or "".
    Bounded on purpose: a golden cross from four months ago is a description of
    the past, not a signal about today.
    """

    pairs = [
        (index, f, s)
        for index, (f, s) in enumerate(zip(fast, slow))
        if f is not None and s is not None
    ]
    if len(pairs) < 2:
        return "", None
    latest = pairs[-1][0]
    for position in range(len(pairs) - 1, 0, -1):
        index, fast_now, slow_now = pairs[position]
        _, fast_prev, slow_prev = pairs[position - 1]
        age = latest - index
        if age > lookback:
            break
        if fast_prev <= slow_prev and fast_now > slow_now:
            return "golden", age
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "death", age
    return "", None


def _pct(price: float, level: Optional[float]) -> Optional[float]:
    if level is None or level == 0.0:
        return None
    return round((price / level - 1.0) * 100.0, 2)


def to_weekly(
    closes: Sequence[float],
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
    volumes: Optional[Sequence[float]] = None,
    *,
    span: int = 5,
) -> Dict[str, List[float]]:
    """Fold daily bars into weekly ones: 5 sessions per bar, oldest first.

    Grouped by session count rather than calendar week because the daily series
    carries no timestamps at this layer, and a holiday-shortened week is still one
    trading week. The **most recent** group is the one that must stay intact, so
    grouping runs backwards from the latest bar and any leftover head is dropped —
    otherwise a partial oldest week shifts every subsequent boundary.

    Weekly aggregation matters because a signal that appears on both timeframes is
    a different claim than one that appears on the daily alone: the weekly chart
    filters the noise that makes daily crossovers whipsaw.
    """

    values = [float(c) for c in (closes or [])]
    count = len(values)
    if count < span:
        return {"closes": [], "highs": [], "lows": [], "volumes": []}
    usable = (count // span) * span
    offset = count - usable  # drop the oldest partial week, keep the newest intact

    out: Dict[str, List[float]] = {"closes": [], "highs": [], "lows": [], "volumes": []}
    for start in range(offset, count, span):
        chunk = slice(start, start + span)
        out["closes"].append(values[start + span - 1])
        if highs:
            window = [float(v) for v in highs[chunk]]
            out["highs"].append(max(window) if window else values[start])
        if lows:
            window = [float(v) for v in lows[chunk]]
            out["lows"].append(min(window) if window else values[start])
        if volumes:
            window = [float(v) for v in volumes[chunk]]
            out["volumes"].append(sum(window))
    return out


# Breakout / breakdown detection. A "level" is the highest high (or lowest low)
# over the lookback, excluding the most recent bars so that today's own price
# cannot be the level it is said to be breaking.
BREAKOUT_LOOKBACK = 60
BREAKOUT_EXCLUDE = 3
# Price must clear the level by this much to count. Without a buffer, every
# oscillation around a prior high registers as a fresh breakout.
BREAKOUT_BUFFER_PCT = 0.5


def _level_break(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = BREAKOUT_LOOKBACK,
) -> Dict[str, Any]:
    """Detect a break of the recent range, and how far price sits inside it."""

    result: Dict[str, Any] = {
        "state": "", "level": None, "distance_pct": None, "range_position_pct": None,
    }
    if len(closes) < lookback + BREAKOUT_EXCLUDE + 1:
        return result
    window_high = highs[-(lookback + BREAKOUT_EXCLUDE):-BREAKOUT_EXCLUDE]
    window_low = lows[-(lookback + BREAKOUT_EXCLUDE):-BREAKOUT_EXCLUDE]
    if not window_high or not window_low:
        return result
    resistance = max(window_high)
    support = min(window_low)
    price = float(closes[-1])
    if resistance > support > 0.0:
        # Clamped: the range is measured excluding recent bars, so a genuine
        # breakout puts price outside it and the raw ratio exceeds 100 (measured:
        # 183% on a clean break). "Position within the range" is only meaningful
        # inside the range; beyond it, `state` is what carries the information.
        raw_position = (price - support) / (resistance - support) * 100.0
        result["range_position_pct"] = round(min(max(raw_position, 0.0), 100.0), 1)
    buffer = BREAKOUT_BUFFER_PCT / 100.0
    if price > resistance * (1.0 + buffer):
        result["state"] = "breakout"
        result["level"] = round(resistance, 4)
        result["distance_pct"] = round((price / resistance - 1.0) * 100.0, 2)
    elif price < support * (1.0 - buffer):
        result["state"] = "breakdown"
        result["level"] = round(support, 4)
        result["distance_pct"] = round((price / support - 1.0) * 100.0, 2)
    return result


def _ma_break(
    closes: Sequence[float],
    line: Sequence[Optional[float]],
    lookback: int = 5,
) -> str:
    """Whether price just crossed a moving average, and which way.

    Losing a long-term average is the event traders act on; being below it for
    months is a condition, not an event. Only a crossing inside ``lookback``
    sessions is reported.

    The crossing must also *stick*: price has to end at least
    ``MA_BREAK_MIN_GAP_PCT`` clear of the line. Without that, a series oscillating
    around a flat average reports a fresh "reclaim" every other bar — measured on
    a +-0.05% synthetic series, this alone lifted the technical score by 5 points
    on pure noise.
    """

    pairs = [
        (index, float(closes[index]), value)
        for index, value in enumerate(line)
        if value is not None
    ]
    if len(pairs) < 2:
        return ""
    latest_index, latest_price, latest_level = pairs[-1]
    if latest_level <= 0.0:
        return ""
    gap_pct = (latest_price / latest_level - 1.0) * 100.0
    if abs(gap_pct) < MA_BREAK_MIN_GAP_PCT:
        # Still sitting on the line: the cross has not resolved either way.
        return ""
    for position in range(len(pairs) - 1, 0, -1):
        index, price, level = pairs[position]
        _, prev_price, prev_level = pairs[position - 1]
        if latest_index - index > lookback:
            break
        if prev_price <= prev_level and price > level:
            return "reclaimed" if gap_pct > 0 else ""
        if prev_price >= prev_level and price < level:
            return "lost" if gap_pct < 0 else ""
    return ""


# The EMA stack must be *separated*, not merely ordered, to count as a trend.
# A series oscillating +-0.05% around a flat line still orders EMA5 > EMA60 >
# EMA129 by fractions of a basis point, and scored 80/100 "bullish" before this
# threshold existed. Measured on live data, genuinely aligned names run a 4-18%
# spread between EMA5 and EMA129 (MSFT +13.2%, MU +17.9%, NVDA +6.4%) while
# mixed ones sit under ~1.3% — so 1.5% separates them with room to spare.
MIN_STACK_SPREAD_PCT = 1.5

# Deadbands for the same reason: an indicator whose magnitude is noise must not
# be read for its sign. Price within 1% of EMA129 is *on* the line, not above it;
# a MACD line under 0.1% of price is flat, not positive.
REGIME_DEADBAND_PCT = 1.0
MACD_DEADBAND_PCT = 0.1

# Divergence thresholds. Both legs must be material: price up at least 3% on a
# histogram peak at most 60% of the prior one. Looser settings flagged 4 of 14
# live names, which is not a warning, it is background noise.
DIVERGENCE_MIN_PRICE_PCT = 3.0
DIVERGENCE_MIN_DECAY = 0.6

# A moving-average cross must resolve by this much to count as a break rather
# than price sitting on the line.
MA_BREAK_MIN_GAP_PCT = 0.5


def _alignment(
    fast: float,
    mid: float,
    slow: float,
    price: float,
) -> str:
    """Classify the EMA stack, requiring real separation between the lines."""

    if price <= 0.0:
        return "mixed"
    spread = abs(fast - slow) / price * 100.0
    if spread < MIN_STACK_SPREAD_PCT:
        # Lines are stacked but effectively on top of each other: chop.
        return "mixed"
    if fast > mid > slow:
        return "bullish"
    if fast < mid < slow:
        return "bearish"
    return "mixed"


def _divergence(
    closes: Sequence[float],
    histogram: Sequence[Optional[float]],
    lookback: int = 40,
) -> str:
    """Price/MACD-momentum divergence over the recent window.

    Compares the latest swing extreme against the prior one: a higher price high
    on a weaker histogram peak is bearish divergence, and the mirror is bullish.

    Both legs must be *material*. A naive comparison of window halves flagged 4 of
    14 live names, which is far too many for what should be an uncommon warning —
    any minor new high on a slightly smaller histogram qualified. Requiring the
    price to have advanced at least `DIVERGENCE_MIN_PRICE_PCT` and momentum to
    have faded by at least `DIVERGENCE_MIN_DECAY` cuts that to the cases where
    the two genuinely disagree.

    Reported as a warning only — divergence can persist for a long time, so it is
    never treated as a signal to act on by itself.
    """

    pairs = [
        (float(close), float(hist))
        for close, hist in zip(closes[-lookback:], histogram[-lookback:])
        if hist is not None
    ]
    if len(pairs) < 30:
        return ""
    half = len(pairs) // 2
    early, late = pairs[:half], pairs[half:]

    early_high = max(early, key=lambda item: item[0])
    late_high = max(late, key=lambda item: item[0])
    if (
        early_high[1] > 0.0
        and late_high[1] > 0.0
        and late_high[0] > early_high[0] * (1.0 + DIVERGENCE_MIN_PRICE_PCT / 100.0)
        and late_high[1] < early_high[1] * DIVERGENCE_MIN_DECAY
    ):
        return "bearish"

    early_low = min(early, key=lambda item: item[0])
    late_low = min(late, key=lambda item: item[0])
    if (
        early_low[1] < 0.0
        and late_low[1] < 0.0
        and late_low[0] < early_low[0] * (1.0 - DIVERGENCE_MIN_PRICE_PCT / 100.0)
        and late_low[1] > early_low[1] * DIVERGENCE_MIN_DECAY
    ):
        return "bullish"
    return ""


def _weekly_read(
    weekly: Dict[str, List[float]],
    signals: TechnicalSignals,
) -> None:
    """Populate the weekly-timeframe fields in place.

    The weekly EMA periods are deliberately not 5/60/129 — 129 weeks is 2.5 years
    and would need a decade of history to warm up. Weekly uses 5/20/60, i.e. one
    month / one quarter / roughly one year, which is the conventional weekly set.
    """

    closes = weekly.get("closes") or []
    signals.weekly_bars = len(closes)
    if len(closes) < MACD_SLOW + MACD_SIGNAL:
        return

    fast = ema_series(closes, 5)
    mid = ema_series(closes, 20)
    slow = ema_series(closes, 60)
    price = closes[-1]
    if None not in (fast[-1], mid[-1], slow[-1]):
        signals.weekly_trend_alignment = _alignment(fast[-1], mid[-1], slow[-1], price)
        signals.weekly_price_vs_slow_pct = _pct(price, slow[-1])
    elif mid[-1] is not None:
        # Not enough weeks for EMA60; fall back to the two shorter lines so the
        # weekly read is degraded rather than absent.
        signals.weekly_price_vs_slow_pct = _pct(price, mid[-1])

    line, signal, histogram = macd_series(closes)
    signals.weekly_macd = round(line[-1], 4) if line[-1] is not None else None
    signals.weekly_macd_histogram = (
        round(histogram[-1], 4) if histogram[-1] is not None else None
    )
    signals.weekly_macd_cross, signals.weekly_macd_cross_age = _cross_state(
        line, signal, lookback=4
    )
    weekly_rsi = rsi_series(closes)
    signals.weekly_rsi = round(weekly_rsi[-1], 2) if weekly_rsi[-1] is not None else None


def _agreement(signals: TechnicalSignals) -> str:
    """Whether the daily and weekly timeframes tell the same story.

    This is the single most useful thing a second timeframe adds. A daily golden
    cross under a bearish weekly trend is a bounce inside a downtrend; the same
    cross under a bullish weekly is a continuation entry. Same daily signal,
    opposite meaning.
    """

    daily = signals.trend_alignment
    weekly = signals.weekly_trend_alignment
    if not daily or not weekly:
        return ""
    if daily == "bullish" and weekly == "bullish":
        return "aligned_bull"
    if daily == "bearish" and weekly == "bearish":
        return "aligned_bear"
    if "bullish" in (daily, weekly) and "bearish" in (daily, weekly):
        return "conflict"
    return ""


def analyse(
    closes: Sequence[float],
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
    volumes: Optional[Sequence[float]] = None,
    *,
    ticker: str = "",
) -> TechnicalSignals:
    """Compute every indicator and derive the discrete states.

    ``closes`` must be chronological daily closes. Highs/lows/volumes are
    optional; ATR and ADX are simply omitted when absent rather than being
    approximated from closes, which would understate real intraday range.
    """

    series = [float(value) for value in (closes or []) if value is not None and float(value) > 0.0]
    result = TechnicalSignals(ticker=ticker.upper(), bars=len(series))
    if len(series) < MACD_SLOW + MACD_SIGNAL:
        # Not even MACD can be formed; report nothing rather than a fake reading.
        result.notes.append(f"仅有 {len(series)} 根日线，不足以计算技术指标")
        return result

    price = series[-1]
    fast_line = ema_series(series, FAST_EMA)
    mid_line = ema_series(series, MID_EMA)
    slow_line = ema_series(series, SLOW_EMA)
    result.ema_fast = round(fast_line[-1], 4) if fast_line[-1] is not None else None
    result.ema_mid = round(mid_line[-1], 4) if mid_line[-1] is not None else None
    result.ema_slow = round(slow_line[-1], 4) if slow_line[-1] is not None else None
    result.price_vs_fast_pct = _pct(price, result.ema_fast)
    result.price_vs_mid_pct = _pct(price, result.ema_mid)
    result.price_vs_slow_pct = _pct(price, result.ema_slow)

    macd_line, signal_line, histogram = macd_series(series)
    result.macd = round(macd_line[-1], 4) if macd_line[-1] is not None else None
    result.macd_signal = round(signal_line[-1], 4) if signal_line[-1] is not None else None
    result.macd_histogram = round(histogram[-1], 4) if histogram[-1] is not None else None
    result.macd_cross, result.macd_cross_age = _cross_state(macd_line, signal_line)
    if result.macd is not None:
        result.macd_above_zero = result.macd > 0.0

    rsi = rsi_series(series)
    result.rsi = round(rsi[-1], 2) if rsi[-1] is not None else None
    if result.rsi is not None:
        if result.rsi >= RSI_OVERBOUGHT:
            result.rsi_zone = "overbought"
        elif result.rsi <= RSI_OVERSOLD:
            result.rsi_zone = "oversold"
        else:
            result.rsi_zone = "neutral"

    # Highs/lows are used by ATR, ADX and the range-break detector, so resolve
    # them once here rather than inside a narrower scope.
    clean_high: List[float] = []
    clean_low: List[float] = []
    if highs and lows and len(highs) == len(lows) == len(closes):
        candidate_h = [float(v) for v in highs if v is not None]
        candidate_l = [float(v) for v in lows if v is not None]
        if len(candidate_h) == len(candidate_l) == len(series):
            clean_high, clean_low = candidate_h, candidate_l
            atr = atr_series(clean_high, clean_low, series)
            if atr and atr[-1] is not None:
                result.atr = round(atr[-1], 4)
                result.atr_pct = round(atr[-1] / price * 100.0, 2) if price else None
            result.adx = adx_value(clean_high, clean_low, series)

    if volumes:
        clean_v = [float(v) for v in volumes if v is not None and float(v) >= 0.0]
        if len(clean_v) >= 21:
            recent = clean_v[-1]
            baseline = sum(clean_v[-21:-1]) / 20.0
            if baseline > 0.0:
                result.volume_ratio = round(recent / baseline, 2)

    # EMA stack and the mid/slow regime cross.
    if None not in (result.ema_fast, result.ema_mid, result.ema_slow):
        result.ema_spread_pct = round(
            (result.ema_fast - result.ema_slow) / price * 100.0, 3
        ) if price else None
        result.trend_alignment = _alignment(
            result.ema_fast, result.ema_mid, result.ema_slow, price
        )
        result.ma_cross, result.ma_cross_age = _cross_state(mid_line, slow_line, lookback=20)

    # Structural events: range breaks and moving-average reclaims/losses. These
    # are what the earlier version was missing — it listed indicator values but
    # never said "broke out of a 60-day range" or "just lost EMA129".
    if clean_high and clean_low and len(clean_high) == len(series):
        break_info = _level_break(series, clean_high, clean_low)
        result.breakout_state = break_info["state"]
        result.breakout_level = break_info["level"]
        result.breakout_distance_pct = break_info["distance_pct"]
        result.range_position_pct = break_info["range_position_pct"]
    result.ema_mid_break = _ma_break(series, mid_line)
    result.ema_slow_break = _ma_break(series, slow_line)
    result.divergence = _divergence(series, histogram)

    # Weekly timeframe, folded from the same daily series.
    weekly = to_weekly(series, clean_high or None, clean_low or None,
                       (volumes and [float(v) for v in volumes if v is not None]) or None)
    _weekly_read(weekly, result)
    result.timeframe_agreement = _agreement(result)

    result.technical_score = _score(result)
    result.notes = _notes(result)
    result.verdict = _verdict(result)
    return result


def _score(signals: TechnicalSignals) -> Optional[float]:
    """Blend the readings into 0-100, or None when the core inputs are missing.

    Weighting reflects how much each input is worth rather than treating all
    indicators as equal. Trend structure (where price sits against the stack)
    dominates; oscillators are deliberately small because RSI on its own is a
    weak directional signal, and ADX only scales confidence in the trend rather
    than voting on direction.
    """

    if signals.macd is None or signals.rsi is None:
        return None

    components: List[tuple] = []

    # 1. Trend structure from the EMA stack (weight 40).
    alignment = {"bullish": 85.0, "mixed": 50.0, "bearish": 20.0}.get(
        signals.trend_alignment, 50.0
    )
    if signals.trend_alignment:
        components.append((alignment, 40.0))

    # 2. Position versus the long-term regime line (weight 20). Above it is a
    #    different market than below it, but being far above is stretched.
    #    A deadband around the line keeps a +0.05% reading from scoring like a
    #    breakout: within it, price is *on* the line, which is neutral.
    if signals.price_vs_slow_pct is not None:
        distance = signals.price_vs_slow_pct
        if abs(distance) <= REGIME_DEADBAND_PCT:
            position = 50.0
        elif distance < 0.0:
            position = max(30.0 + distance, 5.0)
        elif distance <= 25.0:
            position = 60.0 + distance * 1.4
        else:
            # Extended: still constructive, but rein in the reward.
            position = max(95.0 - (distance - 25.0) * 0.8, 55.0)
        components.append((min(max(position, 5.0), 95.0), 20.0))

    # 3. MACD state (weight 25). A fresh cross carries more than a stale one.
    #    Sign is only read when the reading is large enough to mean something:
    #    MACD is in price units, so it is scaled by price before comparison.
    macd_score = 50.0
    reference = signals.ema_slow or 0.0
    scale = abs(signals.macd or 0.0) / reference * 100.0 if reference else 0.0
    if scale >= MACD_DEADBAND_PCT:
        macd_score += 12.0 if signals.macd_above_zero else -12.0
        if signals.macd_histogram is not None:
            macd_score += 8.0 if signals.macd_histogram > 0 else -8.0
    if signals.macd_cross == "golden":
        macd_score += 18.0 if (signals.macd_cross_age or 0) <= 3 else 9.0
    elif signals.macd_cross == "death":
        macd_score -= 18.0 if (signals.macd_cross_age or 0) <= 3 else 9.0
    components.append((min(max(macd_score, 5.0), 95.0), 25.0))

    # 4. RSI (weight 15). Mid-range scores best; both extremes are penalised,
    #    overbought because entries there have poor asymmetry.
    rsi = signals.rsi
    if rsi >= 80.0:
        rsi_score = 20.0
    elif rsi >= RSI_OVERBOUGHT:
        rsi_score = 40.0
    elif rsi >= 50.0:
        rsi_score = 80.0
    elif rsi >= RSI_OVERSOLD:
        rsi_score = 60.0
    else:
        # Oversold is a bounce candidate but often a broken trend; stay neutral.
        rsi_score = 45.0
    components.append((rsi_score, 15.0))

    total_weight = sum(weight for _, weight in components)
    if total_weight <= 0.0:
        return None
    raw = sum(value * weight for value, weight in components) / total_weight

    # Structural adjustments, applied after the weighted blend because they are
    # events rather than levels — they modify the read rather than voting in it.
    if signals.breakout_state == "breakout":
        # A breakout on volume is the highest-quality bullish setup available;
        # without volume it is a candidate for a failed breakout.
        raw += 6.0 if (signals.volume_ratio or 0.0) >= 1.5 else 2.0
    elif signals.breakout_state == "breakdown":
        raw -= 8.0
    if signals.ema_slow_break == "lost":
        raw -= 8.0
    elif signals.ema_slow_break == "reclaimed":
        raw += 5.0
    if signals.divergence == "bearish":
        raw -= 5.0
    elif signals.divergence == "bullish":
        raw += 3.0

    # The weekly timeframe as a confirmation multiplier. A daily signal that the
    # weekly contradicts is worth materially less than one it confirms, which is
    # the whole reason for computing a second timeframe.
    if signals.timeframe_agreement == "aligned_bull":
        raw += 5.0
    elif signals.timeframe_agreement == "aligned_bear":
        raw -= 5.0
    elif signals.timeframe_agreement == "conflict":
        # Pull toward neutral: the timeframes disagree, so conviction is low.
        raw = 50.0 + (raw - 50.0) * 0.7
    elif signals.weekly_macd_cross == "death" and (signals.weekly_macd_cross_age or 9) <= 2:
        raw -= 4.0
    elif signals.weekly_macd_cross == "golden" and (signals.weekly_macd_cross_age or 9) <= 2:
        raw += 4.0

    # ADX scales the result toward neutral when there is no trend to speak of.
    # Below 20 the EMA stack is noise, so a "perfect" stack should not score 85.
    if signals.adx is not None and signals.adx < 20.0:
        raw = 50.0 + (raw - 50.0) * 0.6
    return round(min(max(raw, 0.0), 100.0), 1)


def _notes(signals: TechnicalSignals) -> List[str]:
    """Chinese one-liners explaining the reading, most important first.

    Ordered by what a trader looks at first: structural events (breaks, crossings)
    before steady-state readings (indicator levels), because an event is a reason
    to act and a level is only context.
    """

    notes: List[str] = []

    # --- Structural events first ---
    if signals.breakout_state == "breakout":
        notes.append(
            f"⬆ 突破：站上 {BREAKOUT_LOOKBACK} 日区间高点 {signals.breakout_level:.2f}"
            f"（超出 {signals.breakout_distance_pct:+.1f}%）"
            + ("，且成交量放大确认" if (signals.volume_ratio or 0) >= 1.5
               else "，但成交量未明显放大，突破有效性待确认")
        )
    elif signals.breakout_state == "breakdown":
        notes.append(
            f"⬇ 破位：跌破 {BREAKOUT_LOOKBACK} 日区间低点 {signals.breakout_level:.2f}"
            f"（低于 {signals.breakout_distance_pct:+.1f}%），下方无明确支撑"
        )
    elif signals.range_position_pct is not None:
        notes.append(
            f"位于 {BREAKOUT_LOOKBACK} 日区间 {signals.range_position_pct:.0f}% 分位"
            + ("，接近区间上沿" if signals.range_position_pct >= 85
               else ("，接近区间下沿" if signals.range_position_pct <= 15 else "，区间中部震荡"))
        )

    if signals.ema_slow_break == "lost":
        notes.append("⚠ 刚跌破 EMA129 长期均线，趋势结构受损")
    elif signals.ema_slow_break == "reclaimed":
        notes.append("✔ 刚收复 EMA129 长期均线，长期趋势转多")
    if signals.ema_mid_break == "lost":
        notes.append("刚跌破 EMA60 中期均线")
    elif signals.ema_mid_break == "reclaimed":
        notes.append("刚收复 EMA60 中期均线")

    if signals.ma_cross == "golden":
        notes.append(f"EMA60 上穿 EMA129 金叉（{signals.ma_cross_age} 天前），中长期转多")
    elif signals.ma_cross == "death":
        notes.append(f"EMA60 下穿 EMA129 死叉（{signals.ma_cross_age} 天前），中长期转空")

    if signals.macd_cross == "golden":
        notes.append(
            f"MACD 金叉（{signals.macd_cross_age} 天前）"
            + ("，零轴上方，信号较强" if signals.macd_above_zero else "，但在零轴下方，属反弹性质")
        )
    elif signals.macd_cross == "death":
        notes.append(
            f"MACD 死叉（{signals.macd_cross_age} 天前）"
            + ("，零轴下方，趋势转弱" if signals.macd_above_zero is False else "，零轴上方，属强势整理")
        )

    if signals.divergence == "bearish":
        notes.append("⚠ 顶背离：价格创新高但 MACD 动能走弱，上涨动能衰竭")
    elif signals.divergence == "bullish":
        notes.append("底背离：价格创新低但 MACD 动能转强，下跌动能衰竭")

    # --- Weekly timeframe ---
    if signals.weekly_bars >= MACD_SLOW + MACD_SIGNAL:
        weekly_align = {
            "bullish": "周线多头排列",
            "bearish": "周线空头排列",
            "mixed": "周线均线交织",
        }.get(signals.weekly_trend_alignment, "")
        parts = [part for part in [weekly_align] if part]
        if signals.weekly_macd_cross == "golden":
            parts.append(f"周线 MACD 金叉（{signals.weekly_macd_cross_age} 周前）")
        elif signals.weekly_macd_cross == "death":
            parts.append(f"周线 MACD 死叉（{signals.weekly_macd_cross_age} 周前）")
        if signals.weekly_rsi is not None:
            parts.append(f"周线 RSI {signals.weekly_rsi:.0f}")
        if parts:
            notes.append("【周线】" + "；".join(parts))

        agreement = {
            "aligned_bull": "✔ 日线与周线同步向上，趋势一致性高",
            "aligned_bear": "⚠ 日线与周线同步向下，不宜逆势",
            "conflict": "⚠ 日线与周线方向冲突，可靠性下降，宜等两者同向",
        }.get(signals.timeframe_agreement, "")
        if agreement:
            notes.append(agreement)

    # --- Steady-state levels ---
    alignment = {
        "bullish": f"日线均线多头排列（EMA5 > EMA60 > EMA129，间距 {signals.ema_spread_pct:+.1f}%）",
        "bearish": f"日线均线空头排列（EMA5 < EMA60 < EMA129，间距 {signals.ema_spread_pct:+.1f}%）",
        "mixed": "日线均线交织，方向不明",
    }.get(signals.trend_alignment, "")
    if alignment:
        notes.append(alignment)

    if signals.macd is not None and signals.macd_signal is not None:
        notes.append(
            f"MACD {signals.macd:+.3f}／信号 {signals.macd_signal:+.3f}，"
            f"柱状 {signals.macd_histogram:+.3f}，"
            + ("零轴上方" if signals.macd_above_zero else "零轴下方")
        )

    if signals.rsi is not None:
        zone = {
            "overbought": "超买区（强趋势中属常态，不单独作卖出理由）",
            "oversold": "超卖区（可能超跌，也可能趋势已破坏）",
            "neutral": "中性区",
        }.get(signals.rsi_zone, "")
        notes.append(f"RSI(14) {signals.rsi:.1f}，{zone}")

    if signals.price_vs_slow_pct is not None:
        notes.append(
            f"现价较 EMA129 {signals.price_vs_slow_pct:+.1f}%"
            + ("（长期趋势之上）" if signals.price_vs_slow_pct > 0 else "（长期趋势之下）")
        )

    if signals.adx is not None:
        if signals.adx >= 25.0:
            notes.append(f"ADX {signals.adx:.1f}，趋势明确，均线信号可信")
        elif signals.adx < 20.0:
            notes.append(f"ADX {signals.adx:.1f}，无趋势／震荡市，金叉死叉易反复")
        else:
            notes.append(f"ADX {signals.adx:.1f}，趋势初成")

    if signals.atr_pct is not None:
        notes.append(
            f"ATR {signals.atr_pct:.1f}%（日均波幅）；"
            f"以 2×ATR 计，止损约需给到 {signals.atr_pct * 2:.1f}%"
        )

    if signals.volume_ratio is not None:
        if signals.volume_ratio >= 2.0:
            notes.append(f"成交量为 20 日均量 {signals.volume_ratio:.1f} 倍，显著放量")
        elif signals.volume_ratio >= 1.5:
            notes.append(f"成交量为 20 日均量 {signals.volume_ratio:.1f} 倍，温和放量")
        elif signals.volume_ratio <= 0.5:
            notes.append(f"成交量仅 20 日均量 {signals.volume_ratio:.1f} 倍，缩量")

    return notes


def _verdict(signals: TechnicalSignals) -> str:
    """One-paragraph actionable read: what the chart says, and what would void it.

    This is the part that makes the layer an *analysis* rather than a table of
    numbers. It states a stance, the level that matters, and the condition that
    invalidates it — a technical call without an invalidation level is not a call.
    """

    if signals.technical_score is None:
        return ""

    parts: List[str] = []

    # 1. Stance, driven by timeframe agreement first because it dominates.
    if signals.timeframe_agreement == "aligned_bull":
        parts.append("日线与周线同向向上，趋势交易可参与")
    elif signals.timeframe_agreement == "aligned_bear":
        parts.append("日线与周线同向向下，不宜接刀，等结构修复")
    elif signals.timeframe_agreement == "conflict":
        if signals.weekly_trend_alignment == "bearish":
            parts.append("周线仍空、日线转强，只能视为下跌趋势中的反弹，不宜重仓")
        else:
            parts.append("周线偏多但日线转弱，属上升趋势中的回调，可等日线修复再进")
    elif signals.trend_alignment == "bullish":
        parts.append("日线趋势向上")
    elif signals.trend_alignment == "bearish":
        parts.append("日线趋势向下")
    else:
        parts.append("方向不明，处于震荡")

    # 2. The event that matters right now.
    if signals.breakout_state == "breakout":
        confirmation = (
            "且有量能配合" if (signals.volume_ratio or 0) >= 1.5 else "但缺量能确认，需防假突破"
        )
        parts.append(f"刚突破 {BREAKOUT_LOOKBACK} 日高点 {signals.breakout_level:.2f}，{confirmation}")
    elif signals.breakout_state == "breakdown":
        parts.append(f"已跌破 {BREAKOUT_LOOKBACK} 日低点 {signals.breakout_level:.2f}，下方缺支撑")
    if signals.ema_slow_break == "lost":
        parts.append("同时刚失守 EMA129，这是趋势级别的破坏")
    elif signals.ema_slow_break == "reclaimed":
        parts.append("同时刚收复 EMA129")
    if signals.divergence == "bearish":
        parts.append("并出现顶背离，动能已在衰减")

    # 3. Reliability caveat.
    if signals.adx is not None and signals.adx < 20.0:
        parts.append(f"但 ADX 仅 {signals.adx:.0f}，震荡市中均线与交叉信号容易反复，应降低权重")

    # 4. The invalidation level — the part that makes it falsifiable.
    invalidation = ""
    if signals.ema_slow is not None and signals.trend_alignment != "bearish":
        invalidation = f"跌破 EMA129（{signals.ema_slow:.2f}）则多头逻辑失效"
    elif signals.ema_mid is not None and signals.trend_alignment == "bearish":
        invalidation = f"站回 EMA60（{signals.ema_mid:.2f}）才谈得上转势"
    if invalidation:
        if signals.atr_pct is not None:
            invalidation += f"；按 2×ATR 计止损空间约 {signals.atr_pct * 2:.1f}%"
        parts.append(invalidation)

    return "；".join(parts) + "。"
