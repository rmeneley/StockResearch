import logging
import re
import requests
from typing import Dict, Any, List, Tuple
from backend.config import settings
from backend.models import SentimentSummary

logger = logging.getLogger(__name__)

BULLISH_KEYWORDS = {
    "surge", "surges", "surged", "surging", "jump", "jumps", "jumped", "jumping",
    "rally", "rallies", "rallied", "gain", "gains", "gained", "rise", "rises", "rose", "rising",
    "soar", "soars", "soared", "soaring", "beat", "beats", "beating", "exceed", "exceeds", "exceeded",
    "outperform", "outperforms", "outperformed", "upgrade", "upgraded", "upgrades", "bull", "bullish",
    "growth", "record", "high", "highs", "profit", "profitable", "profits", "boost", "boosts", "boosted",
    "strong", "stronger", "strength", "upside", "win", "wins", "won", "expansion", "expanding",
    "breakthrough", "breakthroughs", "dividend", "dividends", "buy", "buying", "buyer", "buyers",
    "positive", "leader", "leading", "milestone", "milestones", "alliance", "partner", "partnership",
    "boom", "booming", "contract", "contracts", "awarded", "recovery", "recover", "recovering",
    "rebound", "rebounds", "rebounded", "innovation", "innovative", "demand", "advancing", "advance",
}

BEARISH_KEYWORDS = {
    "plunge", "plunges", "plunged", "plunging", "slump", "slumps", "slumped", "slumping",
    "drop", "drops", "dropped", "dropping", "fall", "falls", "fell", "falling",
    "decline", "declines", "declined", "declining", "miss", "misses", "missed", "missing",
    "underperform", "underperformed", "underperforms", "downgrade", "downgraded", "downgrades",
    "bear", "bearish", "cut", "cuts", "cutting", "loss", "losses", "losing", "warning", "warns",
    "warned", "warnings", "risk", "risks", "risky", "weak", "weaker", "weakness", "downside",
    "tumble", "tumbles", "tumbled", "tumbling", "lawsuit", "lawsuits", "sued", "suing",
    "investigation", "investigations", "probe", "probes", "fine", "fined", "penalty", "penalties",
    "layoff", "layoffs", "fired", "debt", "default", "struggle", "struggles", "struggled",
    "struggling", "crash", "crashes", "crashed", "caution", "cautious", "headwind", "headwinds",
    "selloff", "selloffs", "retreat", "retreats", "retreated", "scandal", "fraud", "deficit",
    "antitrust", "ban", "banned", "restriction", "restrictions", "tariff", "tariffs", "bankruptcy",
}


def score_headline_sentiment(title: str, summary: str = "") -> Tuple[str, float]:
    """
    Classifies a news article into Bullish, Bearish, or Neutral using financial NLP lexicon.
    Returns (label, score) with score in [-1.0, 1.0].
    """
    full_text = f"{title} {summary}".lower()
    words = set(re.findall(r"[a-zA-Z]+", full_text))
    bull_hits = len(words & BULLISH_KEYWORDS)
    bear_hits = len(words & BEARISH_KEYWORDS)

    if bull_hits > bear_hits:
        score = min(1.0, 0.40 + 0.20 * (bull_hits - bear_hits))
        return "Bullish", round(score, 3)
    elif bear_hits > bull_hits:
        score = max(-1.0, -0.40 - 0.20 * (bear_hits - bull_hits))
        return "Bearish", round(score, 3)
    else:
        return "Neutral", 0.0


def compute_sentiment_from_articles(articles: List[Any]) -> SentimentSummary:
    """Computes aggregate bullish/bearish ratio and sentiment note from news articles."""
    if not articles:
        return SentimentSummary(
            bullish_percent=0.5,
            bearish_percent=0.5,
            articles_analyzed=0,
            status_note="No recent news feeds found",
        )

    bull_count = 0
    bear_count = 0
    neu_count = 0

    for a in articles:
        title = getattr(a, "title", "") or ""
        summary = getattr(a, "summary", "") or ""
        label = getattr(a, "sentiment", None)
        if not label:
            label, _ = score_headline_sentiment(title, summary)

        if label == "Bullish":
            bull_count += 1
        elif label == "Bearish":
            bear_count += 1
        else:
            neu_count += 1

    total = len(articles)
    bull_pct = round((bull_count + 0.5 * neu_count) / total, 3)
    bear_pct = round((bear_count + 0.5 * neu_count) / total, 3)

    if bull_pct >= 0.65:
        tone = "Strong Bullish Bias"
    elif bull_pct >= 0.55:
        tone = "Mild Bullish Bias"
    elif bear_pct >= 0.65:
        tone = "Strong Bearish Bias"
    elif bear_pct >= 0.55:
        tone = "Mild Bearish Bias"
    else:
        tone = "Neutral Balance"

    return SentimentSummary(
        bullish_percent=bull_pct,
        bearish_percent=bear_pct,
        articles_analyzed=total,
        status_note=f"{tone} ({total} live feeds analyzed)",
    )


def fetch_company_sentiment(ticker: str) -> SentimentSummary:
    """
    Fetches company news sentiment.
    1. Tries Finnhub news-sentiment endpoint if configured and available.
    2. Falls back to analyzing live news articles via financial NLP lexicon.
    """
    ticker_clean = ticker.strip().upper()
    api_key = settings.finnhub_api_key.strip()

    # 1. Try Finnhub if key is present
    if api_key:
        try:
            url = "https://finnhub.io/api/v1/news-sentiment"
            params = {"symbol": ticker_clean, "token": api_key}
            response = requests.get(url, params=params, timeout=4.0)

            if response.status_code == 200:
                data = response.json()
                sentiment_data = data.get("sentiment") or {}
                buzz_data = data.get("buzz") or {}
                articles = int(buzz_data.get("articlesInLastWeek", 0))

                bullish = float(sentiment_data.get("bullishPercent", 0.5))
                bearish = float(sentiment_data.get("bearishPercent", 0.5))

                if articles > 0 and (bullish != 0.5 or bearish != 0.5):
                    if bullish == 0 and bearish == 0:
                        bullish, bearish = 0.5, 0.5
                    return SentimentSummary(
                        bullish_percent=round(bullish, 3),
                        bearish_percent=round(bearish, 3),
                        articles_analyzed=articles,
                        status_note=f"Finnhub sentiment ({articles} weekly articles)",
                    )
        except Exception as e:
            logger.debug("Finnhub error for %s: %s", ticker_clean, e)

    # 2. Live News Financial NLP Fallback
    try:
        from backend.services.news_service import fetch_company_news
        articles = fetch_company_news(ticker_clean, limit=12)
        if articles:
            return compute_sentiment_from_articles(articles)
    except Exception as e:
        logger.warning("Error computing news NLP sentiment for %s: %s", ticker_clean, e)

    return SentimentSummary(
        bullish_percent=0.5,
        bearish_percent=0.5,
        articles_analyzed=0,
        status_note="Neutral fallback",
    )
