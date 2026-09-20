import logging
import time
import datetime
from typing import List, Dict, Any, Optional
import yfinance as yf
import requests

from backend.config import settings
from backend.models import NewsArticleItem, NewsResponse

logger = logging.getLogger(__name__)

# Simple in-memory cache: ticker -> (timestamp, List[NewsArticleItem])
_NEWS_CACHE: Dict[str, tuple[float, List[NewsArticleItem]]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutes


def _parse_yfinance_news_item(item: Dict[str, Any]) -> Optional[NewsArticleItem]:
    """Safely extracts headline, publisher, date, url, thumbnail, and snippet."""
    if not isinstance(item, dict):
        return None

    content = item.get("content")
    if isinstance(content, dict):
        # Modern yfinance format
        title = content.get("title") or "Untitled"
        summary = content.get("summary") or ""
        
        # Provider / Publisher
        provider_obj = content.get("provider")
        publisher = provider_obj.get("displayName") if isinstance(provider_obj, dict) else "Market News"
        
        # URL
        canonical = content.get("canonicalUrl")
        click_through = content.get("clickThroughUrl")
        url = ""
        if isinstance(canonical, dict):
            url = canonical.get("url", "")
        if not url and isinstance(click_through, dict):
            url = click_through.get("url", "")
        if not url:
            url = item.get("link", "")
            
        # Publication Date
        published_at = content.get("pubDate") or content.get("displayTime") or ""
        
        # Thumbnail
        thumb_obj = content.get("thumbnail")
        thumbnail = ""
        if isinstance(thumb_obj, dict):
            resolutions = thumb_obj.get("resolutions")
            if isinstance(resolutions, list) and len(resolutions) > 0:
                thumbnail = resolutions[0].get("url", "")
            if not thumbnail:
                thumbnail = thumb_obj.get("originalUrl", "")
    else:
        # Classic yfinance format
        title = item.get("title") or "Untitled"
        summary = item.get("summary") or ""
        publisher = item.get("publisher") or "Market News"
        url = item.get("link") or ""
        
        raw_ts = item.get("providerPublishTime")
        published_at = ""
        if raw_ts:
            try:
                published_at = datetime.datetime.fromtimestamp(raw_ts, tz=datetime.timezone.utc).isoformat()
            except Exception:
                published_at = str(raw_ts)
                
        thumb_obj = item.get("thumbnail")
        thumbnail = ""
        if isinstance(thumb_obj, dict):
            resolutions = thumb_obj.get("resolutions")
            if isinstance(resolutions, list) and len(resolutions) > 0:
                thumbnail = resolutions[0].get("url", "")
            if not thumbnail:
                thumbnail = thumb_obj.get("originalUrl", "")

    if not title or title == "Untitled":
        return None

    clean_title = title.strip()
    clean_summary = summary.strip() if summary else ""

    from backend.services.sentiment_service import score_headline_sentiment
    sentiment_label, sentiment_score = score_headline_sentiment(clean_title, clean_summary)

    return NewsArticleItem(
        title=clean_title,
        publisher=publisher.strip() if publisher else "Financial News",
        published_at=published_at,
        url=url,
        summary=clean_summary if clean_summary else None,
        thumbnail=thumbnail if thumbnail else None,
        sentiment=sentiment_label,
        sentiment_score=sentiment_score,
    )



def _fetch_finnhub_news(ticker: str, limit: int = 10) -> List[NewsArticleItem]:
    """Fallback to Finnhub company-news if key is available."""
    api_key = settings.finnhub_api_key.strip()
    if not api_key:
        return []

    try:
        today = datetime.date.today()
        from_date = today - datetime.timedelta(days=7)
        url = "https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": ticker.upper(),
            "from": from_date.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "token": api_key,
        }
        res = requests.get(url, params=params, timeout=4.0)
        if res.status_code != 200:
            return []

        articles = []
        for raw in res.json()[:limit]:
            ts = raw.get("datetime")
            dt_str = ""
            if ts:
                try:
                    dt_str = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
                except Exception:
                    pass
            h_title = raw.get("headline", "Untitled")
            h_summary = raw.get("summary", "")
            from backend.services.sentiment_service import score_headline_sentiment
            lbl, sc = score_headline_sentiment(h_title, h_summary)

            articles.append(
                NewsArticleItem(
                    title=h_title,
                    publisher=raw.get("source", "Finnhub"),
                    published_at=dt_str,
                    url=raw.get("url", ""),
                    summary=h_summary if h_summary else None,
                    thumbnail=raw.get("image") or None,
                    sentiment=lbl,
                    sentiment_score=sc,
                )
            )
        return articles

    except Exception as e:
        logger.debug("Finnhub company news error for %s: %s", ticker, e)
        return []


def fetch_company_news(ticker: str, limit: int = 15, force_refresh: bool = False) -> List[NewsArticleItem]:
    """
    Fetches the latest company news articles for a given ticker.
    Uses in-memory TTL caching, yfinance live feeds, and Finnhub fallback.
    """
    ticker_clean = ticker.strip().upper()
    now = time.time()

    if not force_refresh and ticker_clean in _NEWS_CACHE:
        cached_time, cached_items = _NEWS_CACHE[ticker_clean]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_items

    articles: List[NewsArticleItem] = []

    # 1. Try yfinance
    try:
        t = yf.Ticker(ticker_clean)
        raw_news = t.news or []
        for item in raw_news:
            parsed = _parse_yfinance_news_item(item)
            if parsed and parsed.url:
                articles.append(parsed)
            if len(articles) >= limit:
                break
    except Exception as e:
        logger.warning("Error fetching yfinance news for %s: %s", ticker_clean, e)

    # 2. Fallback to Finnhub if yfinance returned nothing
    if not articles:
        articles = _fetch_finnhub_news(ticker_clean, limit=limit)

    _NEWS_CACHE[ticker_clean] = (now, articles)
    return articles

