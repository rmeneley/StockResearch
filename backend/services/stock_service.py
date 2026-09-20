import datetime
import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import (
    StockMetricCache,
    StockRankingItem,
    TechnicalSummary,
    InsiderSummary,
    SentimentSummary,
    StrategyWeights,
)
from backend.services.technical_service import fetch_technical_data
from backend.services.insider_service import fetch_and_cache_insider_data
from backend.services.sentiment_service import fetch_company_sentiment
from backend.services.scoring_engine import (
    normalize_technical,
    normalize_volume,
    normalize_insider,
    normalize_sentiment,
    calculate_composite_score,
    classify_signal,
)

logger = logging.getLogger(__name__)

DEFAULT_UNIVERSE = [
    "NVDA",
    "INTC",
    "OXY",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AMD",
    "JPM",
    "LLY",
]


def is_cache_valid(updated_at: Optional[datetime.datetime]) -> bool:
    """Checks if the cached record is within the TTL window."""
    if not updated_at:
        return False
    expiration_limit = datetime.datetime.utcnow() - datetime.timedelta(minutes=settings.cache_ttl_minutes)
    return updated_at >= expiration_limit


def get_or_update_stock_metric(ticker: str, db: Session, force_refresh: bool = False) -> StockMetricCache:
    """
    Retrieves stock metrics from SQLite cache if fresh, otherwise recalculates
    from yfinance, SEC EDGAR Form 4 filings, and Finnhub news sentiment.
    """
    ticker_clean = ticker.strip().upper()
    cached = db.query(StockMetricCache).filter(StockMetricCache.ticker == ticker_clean).first()

    if cached and is_cache_valid(cached.updated_at) and not force_refresh:
        return cached

    logger.info("Refreshing metrics for %s (force_refresh=%s)...", ticker_clean, force_refresh)

    # 1. Fetch technicals
    tech_data = fetch_technical_data(ticker_clean)
    price = tech_data["current_price"]
    price_change = tech_data["price_change_pct"]
    rsi = tech_data["rsi"]
    ema20 = tech_data["ema_20"]
    ema50 = tech_data["ema_50"]
    macd_hist = tech_data["macd_hist"]
    rvol = tech_data["rvol"]
    company_name = tech_data["company_name"]

    # 2. Fetch Form 4 insider buys
    insider_summary, _ = fetch_and_cache_insider_data(ticker_clean, db, force_refresh=force_refresh)

    # 3. Fetch sentiment
    sentiment_summary = fetch_company_sentiment(ticker_clean)

    # 4. Calculate normalized scores
    s_tech, _ = normalize_technical(rsi, ema20, ema50, macd_hist, price)
    s_vol = normalize_volume(rvol, price_change)
    s_insider = normalize_insider(
        total_buy_value=insider_summary.total_buy_value,
        unique_buyers=insider_summary.unique_insiders_count,
        has_discretionary_buy=insider_summary.has_discretionary_buy,
        buy_count=insider_summary.recent_buys_count,
        total_sell_value=insider_summary.total_sell_value,
        has_discretionary_sell=insider_summary.has_discretionary_sell,
        sell_count=insider_summary.recent_sells_count,
    )
    s_sent = normalize_sentiment(
        sentiment_summary.bullish_percent,
        sentiment_summary.bearish_percent,
    )

    if not cached:
        cached = StockMetricCache(ticker=ticker_clean)
        db.add(cached)

    cached.company_name = company_name
    cached.current_price = price
    cached.price_change_pct = price_change
    cached.rsi = rsi
    cached.ema_20 = ema20
    cached.ema_50 = ema50
    cached.macd_line = tech_data["macd_line"]
    cached.macd_signal = tech_data["macd_signal"]
    cached.macd_hist = macd_hist
    cached.rvol = rvol

    cached.technical_score = s_tech
    cached.volume_score = s_vol
    cached.insider_score = s_insider
    cached.sentiment_score = s_sent

    cached.next_earnings_date = tech_data.get("next_earnings_date")
    cached.insider_summary_json = json.dumps(insider_summary.model_dump())
    cached.sentiment_details_json = json.dumps(sentiment_summary.model_dump())
    cached.updated_at = datetime.datetime.utcnow()

    db.commit()
    db.refresh(cached)
    return cached


def build_stock_ranking_item(cached: StockMetricCache, weights: StrategyWeights) -> StockRankingItem:
    """Constructs a StockRankingItem with dynamic composite score based on current weights."""
    comp_score = calculate_composite_score(
        s_tech=cached.technical_score,
        s_insider=cached.insider_score,
        s_vol=cached.volume_score,
        s_sent=cached.sentiment_score,
        weights=weights,
    )
    signal = classify_signal(comp_score)

    _, trend_label = normalize_technical(
        rsi=cached.rsi,
        ema_20=cached.ema_20,
        ema_50=cached.ema_50,
        macd_hist=cached.macd_hist,
        price=cached.current_price,
    )

    insider_dict = json.loads(cached.insider_summary_json or "{}")
    sentiment_dict = json.loads(cached.sentiment_details_json or "{}")

    insider = InsiderSummary(**insider_dict) if insider_dict else InsiderSummary()
    sentiment = SentimentSummary(**sentiment_dict) if sentiment_dict else SentimentSummary()

    technicals = TechnicalSummary(
        rsi=cached.rsi,
        ema_20=cached.ema_20,
        ema_50=cached.ema_50,
        macd_hist=cached.macd_hist,
        trend_signal=trend_label,
    )

    return StockRankingItem(
        ticker=cached.ticker,
        company_name=cached.company_name,
        current_price=cached.current_price,
        price_change_pct=cached.price_change_pct,
        composite_score=comp_score,
        signal_label=signal,
        technical_score=cached.technical_score,
        volume_score=cached.volume_score,
        insider_score=cached.insider_score,
        sentiment_score=cached.sentiment_score,
        rsi=cached.rsi,
        rvol=cached.rvol,
        technicals=technicals,
        insider=insider,
        sentiment=sentiment,
        next_earnings_date=cached.next_earnings_date,
        updated_at=cached.updated_at.isoformat() if cached.updated_at else "",
    )



def get_ranked_stocks(
    tickers: List[str],
    weights: StrategyWeights,
    db: Session,
    force_refresh: bool = False
) -> List[StockRankingItem]:
    """Fetches and ranks all tickers by composite score descending."""
    results: List[StockRankingItem] = []
    for ticker in tickers:
        try:
            cached = get_or_update_stock_metric(ticker, db, force_refresh=force_refresh)
            item = build_stock_ranking_item(cached, weights)
            results.append(item)
        except Exception as e:
            logger.error("Error building ranking item for %s: %s", ticker, e)

    # Sort descending by composite score
    results.sort(key=lambda x: x.composite_score, reverse=True)
    return results
