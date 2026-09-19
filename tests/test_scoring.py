import pytest
import pandas as pd
import numpy as np

from backend.models import StrategyWeights
from backend.services.scoring_engine import (
    normalize_technical,
    normalize_volume,
    normalize_insider,
    normalize_sentiment,
    calculate_composite_score,
    classify_signal,
)
from backend.services.technical_service import compute_technicals_from_df


def test_normalize_technical_bounds():
    """Verify technical normalizer stays strictly within [-1.0, 1.0]."""
    # Extremely bullish scenario
    score_bull, label_bull = normalize_technical(
        rsi=85.0, ema_20=115.0, ema_50=100.0, macd_hist=2.5, price=118.0
    )
    assert -1.0 <= score_bull <= 1.0
    assert score_bull > 0.4
    assert "Uptrend" in label_bull

    # Extremely bearish scenario
    score_bear, label_bear = normalize_technical(
        rsi=15.0, ema_20=85.0, ema_50=100.0, macd_hist=-2.5, price=82.0
    )
    assert -1.0 <= score_bear <= 1.0
    assert score_bear < -0.4
    assert "Downtrend" in label_bear

    # Neutral scenario
    score_neutral, label_neutral = normalize_technical(
        rsi=50.0, ema_20=100.0, ema_50=100.0, macd_hist=0.0, price=100.0
    )
    assert abs(score_neutral) < 0.1
    assert "Neutral" in label_neutral


def test_normalize_volume():
    """Verify RVOL volume normalizer reflects direction and bounds."""
    # Breakout volume on green day
    s_green = normalize_volume(rvol=2.5, price_change_pct=3.0)
    assert 0.0 < s_green <= 1.0

    # High volume selloff on red day
    s_red = normalize_volume(rvol=2.5, price_change_pct=-3.0)
    assert -1.0 <= s_red < 0.0

    # Average volume flat day
    s_flat = normalize_volume(rvol=1.0, price_change_pct=0.0)
    assert s_flat == 0.0


def test_normalize_insider():
    """Verify insider conviction parsing and 10b5-1 discretionary distinction."""
    # Zero buys
    assert normalize_insider(total_buy_value=0.0, unique_buyers=0, has_discretionary_buy=False, buy_count=0) == 0.0

    # High conviction cluster discretionary buy
    s_cluster_disc = normalize_insider(
        total_buy_value=500000.0,
        unique_buyers=3,
        has_discretionary_buy=True,
        buy_count=4,
    )
    assert s_cluster_disc >= 0.7

    # 10b5-1 automated plan only
    s_plan_only = normalize_insider(
        total_buy_value=50000.0,
        unique_buyers=1,
        has_discretionary_buy=False,
        buy_count=1,
    )
    assert s_plan_only < s_cluster_disc


def test_normalize_sentiment():
    """Verify Finnhub sentiment score bounds."""
    assert normalize_sentiment(0.75, 0.25) == 0.50
    assert normalize_sentiment(0.20, 0.80) == -0.60
    assert normalize_sentiment(0.50, 0.50) == 0.0


def test_calculate_composite_score_and_weights():
    """Verify weights auto-normalization and composite calculation."""
    weights = StrategyWeights(w_tech=2.0, w_insider=2.0, w_vol=0.0, w_sent=0.0)
    # Normalized weights should be 0.5, 0.5, 0.0, 0.0
    comp = calculate_composite_score(
        s_tech=0.8,
        s_insider=0.6,
        s_vol=-0.5,
        s_sent=-0.5,
        weights=weights,
    )
    # Expected: 0.5*0.8 + 0.5*0.6 = 0.70
    assert comp == 0.70
    assert classify_signal(comp) == "Strong Bullish"

    # Bearish composite
    weights_all = StrategyWeights(w_tech=0.25, w_insider=0.25, w_vol=0.25, w_sent=0.25)
    bear_comp = calculate_composite_score(
        s_tech=-0.6,
        s_insider=0.0,
        s_vol=-0.8,
        s_sent=-0.6,
        weights=weights_all,
    )
    assert bear_comp < -0.40
    assert classify_signal(bear_comp) == "Strong Bearish"


def test_technical_calculation_from_df():
    """Verify indicators computation from OHLCV series."""
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="B")
    prices = 100.0 + np.cumsum(np.random.randn(60) * 1.5)
    volume = np.random.randint(1_000_000, 5_000_000, size=60)
    df = pd.DataFrame({"Close": prices, "Volume": volume}, index=dates)

    indicators = compute_technicals_from_df(df)
    assert "rsi" in indicators
    assert 0 <= indicators["rsi"] <= 100
    assert "ema_20" in indicators
    assert indicators["ema_20"] > 0
    assert "ema_50" in indicators
    assert "macd_hist" in indicators
    assert "rvol" in indicators
    assert indicators["rvol"] > 0

