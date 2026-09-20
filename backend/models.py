import datetime
import json
from typing import List, Optional
from pydantic import BaseModel, Field

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Text,
    create_engine,
    Index,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

Base = declarative_base()

# -----------------------------------------------------------------------------
# SQLAlchemy Database Models
# -----------------------------------------------------------------------------

class StockMetricCache(Base):
    """Caches aggregated technical indicators, insider scores, and sentiment metrics."""
    __tablename__ = "stock_metric_cache"

    ticker = Column(String(16), primary_key=True, index=True)
    company_name = Column(String(128), default="")
    current_price = Column(Float, default=0.0)
    price_change_pct = Column(Float, default=0.0)

    # Technical Indicators
    rsi = Column(Float, default=50.0)
    ema_20 = Column(Float, default=0.0)
    ema_50 = Column(Float, default=0.0)
    macd_line = Column(Float, default=0.0)
    macd_signal = Column(Float, default=0.0)
    macd_hist = Column(Float, default=0.0)
    rvol = Column(Float, default=1.0)

    # Normalized Factor Scores in [-1.0, 1.0]
    technical_score = Column(Float, default=0.0)
    volume_score = Column(Float, default=0.0)
    insider_score = Column(Float, default=0.0)
    sentiment_score = Column(Float, default=0.0)
    composite_score = Column(Float, default=0.0)

    # Serialized JSON summaries
    insider_summary_json = Column(Text, default="{}")
    sentiment_details_json = Column(Text, default="{}")
    next_earnings_date = Column(String(32), nullable=True)
    latest_news_time = Column(String(64), nullable=True)
    latest_news_title = Column(String(256), nullable=True)

    updated_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class InsiderTransactionModel(Base):
    """Caches individual SEC Form 4 Code 'P' transactions."""
    __tablename__ = "insider_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), nullable=False, index=True)
    filing_date = Column(String(32), default="")
    insider_name = Column(String(128), default="")
    insider_title = Column(String(128), default="")
    transaction_code = Column(String(4), default="P")
    is_10b5_1 = Column(Boolean, default=False)
    shares = Column(Float, default=0.0)
    price_per_share = Column(Float, default=0.0)
    total_value = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Index("idx_insider_ticker_date", InsiderTransactionModel.ticker, InsiderTransactionModel.filing_date)


class RemovedTicker(Base):
    """Tracks tickers explicitly removed by the user so they are not auto-seeded or returned."""
    __tablename__ = "removed_tickers"

    ticker = Column(String(16), primary_key=True, index=True)
    removed_at = Column(DateTime, default=datetime.datetime.utcnow)


# -----------------------------------------------------------------------------
# Database Setup & Session Factory
# -----------------------------------------------------------------------------

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initializes tables if they do not exist, and ensures schema migrations."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE stock_metric_cache ADD COLUMN next_earnings_date VARCHAR(32)"))
        except Exception:
            pass  # Already exists
        try:
            conn.execute(text("ALTER TABLE stock_metric_cache ADD COLUMN latest_news_time VARCHAR(64)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE stock_metric_cache ADD COLUMN latest_news_title VARCHAR(256)"))
        except Exception:
            pass




def get_db():
    """FastAPI dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class StrategyWeights(BaseModel):
    w_tech: float = Field(0.35, ge=0.0, description="Technical indicators weight")
    w_insider: float = Field(0.25, ge=0.0, description="Insider conviction weight")
    w_vol: float = Field(0.20, ge=0.0, description="Volume & RVOL weight")
    w_sent: float = Field(0.20, ge=0.0, description="News sentiment weight")

    def normalized(self) -> "StrategyWeights":
        total = self.w_tech + self.w_insider + self.w_vol + self.w_sent
        if total <= 0:
            return StrategyWeights(w_tech=0.25, w_insider=0.25, w_vol=0.25, w_sent=0.25)
        return StrategyWeights(
            w_tech=round(self.w_tech / total, 4),
            w_insider=round(self.w_insider / total, 4),
            w_vol=round(self.w_vol / total, 4),
            w_sent=round(self.w_sent / total, 4),
        )


class InsiderTransactionItem(BaseModel):
    filing_date: str
    insider_name: str
    insider_title: str
    transaction_code: str = "P"  # 'P' for Purchase, 'S' for Sale
    transaction_type: str = "Purchase"  # "Purchase" or "Sale"
    is_10b5_1: bool
    shares: float
    price_per_share: float
    total_value: float


class InsiderSummary(BaseModel):
    recent_buys_count: int = 0
    total_buy_value: float = 0.0
    recent_sells_count: int = 0
    total_sell_value: float = 0.0
    net_value: float = 0.0
    unique_insiders_count: int = 0
    has_discretionary_buy: bool = False
    has_discretionary_sell: bool = False
    last_buy_date: Optional[str] = None
    last_transaction_date: Optional[str] = None


class SentimentSummary(BaseModel):
    bullish_percent: float = 0.5
    bearish_percent: float = 0.5
    articles_analyzed: int = 0
    status_note: str = "Neutral fallback"


class TechnicalSummary(BaseModel):
    rsi: float
    ema_20: float
    ema_50: float
    macd_hist: float
    trend_signal: str  # e.g., "Bullish Uptrend", "Bearish Downtrend", "Neutral"


class StockRankingItem(BaseModel):
    ticker: str
    company_name: str
    current_price: float
    price_change_pct: float
    composite_score: float  # Normalized in [-1.0, 1.0]
    signal_label: str       # "Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"
    technical_score: float  # [-1.0, 1.0]
    volume_score: float     # [-1.0, 1.0]
    insider_score: float    # [-1.0, 1.0]
    sentiment_score: float  # [-1.0, 1.0]
    rsi: float
    rvol: float
    technicals: TechnicalSummary
    insider: InsiderSummary
    sentiment: SentimentSummary
    next_earnings_date: Optional[str] = None
    latest_news_time: Optional[str] = None
    latest_news_title: Optional[str] = None
    updated_at: str



class RankingsResponse(BaseModel):
    stocks: List[StockRankingItem]
    weights: StrategyWeights
    timestamp: str
    total_tracked: int


class InsiderDetailResponse(BaseModel):
    ticker: str
    summary: InsiderSummary
    transactions: List[InsiderTransactionItem]


class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    sec_identity_set: bool
    finnhub_configured: bool
    cached_tickers_count: int


class NewsArticleItem(BaseModel):
    title: str
    publisher: str
    published_at: str
    url: str
    summary: Optional[str] = None
    thumbnail: Optional[str] = None
    sentiment: Optional[str] = "Neutral"
    sentiment_score: Optional[float] = 0.0



class NewsResponse(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    total_articles: int
    articles: List[NewsArticleItem]

