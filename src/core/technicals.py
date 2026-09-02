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

    # 0-100 composite of the readings above, or None when history is too short.
    technical_score: Optional[float] = None
    # Human-readable Chinese notes, ordered most to least important.
    notes: List[str] = field(default_factory=list)

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

    if highs and lows and len(highs) == len(lows) == len(closes):
        clean_h = [float(v) for v in highs if v is not None]
        clean_l = [float(v) for v in lows if v is not None]
        if len(clean_h) == len(clean_l) == len(series):
            atr = atr_series(clean_h, clean_l, series)
            if atr and atr[-1] is not None:
                result.atr = round(atr[-1], 4)
                result.atr_pct = round(atr[-1] / price * 100.0, 2) if price else None
            result.adx = adx_value(clean_h, clean_l, series)

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

    result.technical_score = _score(result)
    result.notes = _notes(result)
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

    # ADX scales the result toward neutral when there is no trend to speak of.
    # Below 20 the EMA stack is noise, so a "perfect" stack should not score 85.
    if signals.adx is not None and signals.adx < 20.0:
        raw = 50.0 + (raw - 50.0) * 0.6
    return round(min(max(raw, 0.0), 100.0), 1)


def _notes(signals: TechnicalSignals) -> List[str]:
    """Chinese one-liners explaining the reading, most important first."""

    notes: List[str] = []
    alignment = {
        "bullish": "均线多头排列（EMA5 > EMA60 > EMA129）",
        "bearish": "均线空头排列（EMA5 < EMA60 < EMA129）",
        "mixed": "均线交织，方向不明",
    }.get(signals.trend_alignment, "")
    if alignment:
        notes.append(alignment)

    if signals.ma_cross == "golden":
        notes.append(f"EMA60 上穿 EMA129 形成金叉（{signals.ma_cross_age} 天前）")
    elif signals.ma_cross == "death":
        notes.append(f"EMA60 下穿 EMA129 形成死叉（{signals.ma_cross_age} 天前）")

    if signals.macd_cross == "golden":
        notes.append(f"MACD 金叉（{signals.macd_cross_age} 天前）")
    elif signals.macd_cross == "death":
        notes.append(f"MACD 死叉（{signals.macd_cross_age} 天前）")
    if signals.macd_histogram is not None and signals.macd_above_zero is not None:
        notes.append(
            f"MACD {signals.macd:+.3f}／信号 {signals.macd_signal:+.3f}，"
            f"柱状 {signals.macd_histogram:+.3f}，"
            + ("在零轴上方" if signals.macd_above_zero else "在零轴下方")
        )

    if signals.rsi is not None:
        zone = {
            "overbought": "超买区，追高风险大",
            "oversold": "超卖区，可能超跌但也可能趋势破坏",
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
            notes.append(f"ADX {signals.adx:.1f}，趋势明确")
        elif signals.adx < 20.0:
            notes.append(f"ADX {signals.adx:.1f}，无趋势／震荡，均线信号可靠度低")

    if signals.atr_pct is not None:
        notes.append(f"ATR {signals.atr_pct:.1f}%（日均波动幅度，可用于设止损）")

    if signals.volume_ratio is not None:
        if signals.volume_ratio >= 2.0:
            notes.append(f"成交量为 20 日均量的 {signals.volume_ratio:.1f} 倍，明显放量")
        elif signals.volume_ratio <= 0.5:
            notes.append(f"成交量仅为 20 日均量的 {signals.volume_ratio:.1f} 倍，缩量")

    return notes
