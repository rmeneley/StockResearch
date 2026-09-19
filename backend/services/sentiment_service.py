import logging
import requests
from typing import Dict, Any
from backend.config import settings
from backend.models import SentimentSummary

logger = logging.getLogger(__name__)

def fetch_company_sentiment(ticker: str) -> SentimentSummary:
    """
    Fetches company news sentiment from Finnhub.
    Computes bullish and bearish proportions.
    Falls back gracefully to neutral sentiment (0.5 / 0.5) if key is missing or limit is exceeded.
    """
    ticker_clean = ticker.strip().upper()
    api_key = settings.finnhub_api_key.strip()

    if not api_key:
        return SentimentSummary(
            bullish_percent=0.5,
            bearish_percent=0.5,
            articles_analyzed=0,
            status_note="No FINNHUB_API_KEY set; neutral sentiment applied",
        )

    try:
        # Finnhub News Sentiment endpoint
        url = "https://finnhub.io/api/v1/news-sentiment"
        params = {"symbol": ticker_clean, "token": api_key}
        response = requests.get(url, params=params, timeout=5.0)

        if response.status_code == 200:
            data = response.json()
            sentiment_data = data.get("sentiment") or {}
            buzz_data = data.get("buzz") or {}

            bullish = float(sentiment_data.get("bullishPercent", 0.5))
            bearish = float(sentiment_data.get("bearishPercent", 0.5))
            articles = int(buzz_data.get("articlesInLastWeek", 0))

            # Normalize in case both sum to 0
            if bullish == 0 and bearish == 0:
                bullish, bearish = 0.5, 0.5

            return SentimentSummary(
                bullish_percent=round(bullish, 3),
                bearish_percent=round(bearish, 3),
                articles_analyzed=articles,
                status_note="Finnhub live sentiment",
            )
        elif response.status_code == 429:
            logger.warning("Finnhub rate limit reached for %s", ticker_clean)
            return SentimentSummary(
                bullish_percent=0.5,
                bearish_percent=0.5,
                articles_analyzed=0,
                status_note="Finnhub rate limit reached (neutral fallback)",
            )
        else:
            logger.warning("Finnhub returned HTTP %s for %s", response.status_code, ticker_clean)
            return SentimentSummary(
                bullish_percent=0.5,
                bearish_percent=0.5,
                articles_analyzed=0,
                status_note=f"Finnhub status {response.status_code} (neutral fallback)",
            )
    except Exception as e:
        logger.warning("Error contacting Finnhub for %s: %s", ticker_clean, e)
        return SentimentSummary(
            bullish_percent=0.5,
            bearish_percent=0.5,
            articles_analyzed=0,
            status_note="Connection error (neutral fallback)",
        )

