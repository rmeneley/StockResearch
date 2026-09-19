import math
from typing import Tuple
from backend.models import StrategyWeights

def normalize_technical(
    rsi: float,
    ema_20: float,
    ema_50: float,
    macd_hist: float,
    price: float
) -> Tuple[float, str]:
    """
    Normalizes technical indicators into a single score bounded in [-1.0, 1.0].
    Also returns a human-readable trend signal label.
    """
    # 1. RSI Score: RSI standard ranges [0, 100], centered around 50
    # RSI = 70 -> +0.8, RSI = 30 -> -0.8
    s_rsi = max(-1.0, min(1.0, (rsi - 50.0) / 25.0))

    # 2. EMA Trend Score (EMA20 vs EMA50 and Price vs EMA20)
    s_ema = 0.0
    if ema_50 > 0 and ema_20 > 0 and price > 0:
        delta_ema = (ema_20 - ema_50) / ema_50
        delta_price = (price - ema_20) / ema_20
        # tanh non-linear saturation
        s_ema = math.tanh(15.0 * delta_ema + 10.0 * delta_price)

    # 3. MACD Histogram Score
    s_macd = 0.0
    if price > 0:
        norm_factor = max(0.005 * price, 0.01)
        s_macd = math.tanh(macd_hist / norm_factor)

    # Blend: 40% RSI, 35% EMA, 25% MACD
    tech_score = 0.40 * s_rsi + 0.35 * s_ema + 0.25 * s_macd
    tech_score = max(-1.0, min(1.0, tech_score))

    # Trend label determination
    if tech_score >= 0.35:
        trend_label = "Strong Uptrend"
    elif tech_score >= 0.10:
        trend_label = "Moderate Uptrend"
    elif tech_score <= -0.35:
        trend_label = "Strong Downtrend"
    elif tech_score <= -0.10:
        trend_label = "Moderate Downtrend"
    else:
        trend_label = "Neutral / Consolidation"

    return round(tech_score, 4), trend_label


def normalize_volume(rvol: float, price_change_pct: float) -> float:
    """
    Normalizes Relative Volume (RVOL) into [-1.0, 1.0].
    High volume on green days = bullish conviction (+).
    High volume on red days = bearish conviction (-).
    """
    if price_change_pct > 0.01:
        direction = 1.0
    elif price_change_pct < -0.01:
        direction = -1.0
    else:
        direction = 0.0

    # RVOL deviation from baseline of 1.0
    # e.g., RVOL = 2.0 with +2% -> (2.0 - 1.0) * 0.6 = +0.6
    vol_impact = (rvol - 1.0) * 0.6
    score = vol_impact * direction
    return round(max(-1.0, min(1.0, score)), 4)


def normalize_insider(
    total_buy_value: float,
    unique_buyers: int,
    has_discretionary_buy: bool,
    buy_count: int
) -> float:
    """
    Normalizes SEC Form 4 open-market buys (Code 'P') into [0.0, 1.0].
    Gives heavy weight to cluster buying and non-10b5-1 (discretionary) conviction.
    """
    if buy_count == 0 or total_buy_value <= 0:
        return 0.0

    # Cluster buying signal: up to 3+ insiders buying yields up to 0.40
    cluster_component = min(unique_buyers, 3) * 0.133  # ~0.40 max

    # Dollar value signal: scaled by $250k benchmark
    value_component = math.tanh(total_buy_value / 250000.0) * 0.40

    # 10b5-1 distinction: discretionary purchases show immediate high conviction
    conviction_component = 0.20 if has_discretionary_buy else 0.05

    score = cluster_component + value_component + conviction_component
    return round(max(0.0, min(1.0, score)), 4)


def normalize_sentiment(bullish_percent: float, bearish_percent: float) -> float:
    """
    Normalizes Finnhub news sentiment into [-1.0, 1.0].
    Net sentiment = Bullish% - Bearish%
    """
    score = bullish_percent - bearish_percent
    return round(max(-1.0, min(1.0, score)), 4)


def calculate_composite_score(
    s_tech: float,
    s_insider: float,
    s_vol: float,
    s_sent: float,
    weights: StrategyWeights
) -> float:
    """
    Computes the composite score using normalized weights:
    S_comp = W_tech * S_tech + W_insider * S_insider + W_vol * S_vol + W_sent * S_sent
    """
    norm_w = weights.normalized()
    comp = (
        norm_w.w_tech * s_tech +
        norm_w.w_insider * s_insider +
        norm_w.w_vol * s_vol +
        norm_w.w_sent * s_sent
    )
    return round(max(-1.0, min(1.0, comp)), 4)


def classify_signal(composite_score: float) -> str:
    """Maps composite score to qualitative rating."""
    if composite_score >= 0.40:
        return "Strong Bullish"
    elif composite_score >= 0.12:
        return "Bullish"
    elif composite_score <= -0.40:
        return "Strong Bearish"
    elif composite_score <= -0.12:
        return "Bearish"
    else:
        return "Neutral"

