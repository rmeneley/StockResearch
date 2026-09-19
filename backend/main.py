import os
import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config import settings, init_edgar_identity
from backend.models import (
    init_db,
    get_db,
    StockMetricCache,
    StrategyWeights,
    RankingsResponse,
    InsiderDetailResponse,
    HealthResponse,
)
from backend.services.stock_service import (
    DEFAULT_UNIVERSE,
    get_ranked_stocks,
    get_or_update_stock_metric,
)
from backend.services.insider_service import fetch_and_cache_insider_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables and SEC Edgar identity
    init_db()
    init_edgar_identity()
    yield


app = FastAPI(
    title="Stock Research & Multi-Factor Ranking API",
    description="Scores and ranks stocks using technical indicators, SEC Form 4 insider conviction, volume, and sentiment.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base directory paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


@app.get("/api/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint validating database connectivity and service configuration."""
    db_connected = False
    cached_count = 0
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
        cached_count = db.query(StockMetricCache).count()
    except Exception:
        db_connected = False

    sec_identity_set = bool(settings.sec_edgar_identity.strip())
    finnhub_configured = bool(settings.finnhub_api_key.strip())

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        db_connected=db_connected,
        sec_identity_set=sec_identity_set,
        finnhub_configured=finnhub_configured,
        cached_tickers_count=cached_count,
    )


@app.get("/api/rankings", response_model=RankingsResponse)
def get_rankings(
    w_tech: float = Query(0.35, ge=0.0, description="Technical indicator weight"),
    w_insider: float = Query(0.25, ge=0.0, description="Insider conviction weight"),
    w_vol: float = Query(0.20, ge=0.0, description="Volume & RVOL weight"),
    w_sent: float = Query(0.20, ge=0.0, description="News sentiment weight"),
    tickers: Optional[str] = Query(None, description="Comma-separated ticker list, e.g. AAPL,MSFT,NVDA"),
    force_refresh: bool = Query(False, description="Force re-fetch from external APIs bypassing cache"),
    db: Session = Depends(get_db),
):
    """
    Computes stock rankings based on dynamic strategy weights.
    Returns individual factor scores, technical indicators, and composite score.
    """
    weights = StrategyWeights(
        w_tech=w_tech,
        w_insider=w_insider,
        w_vol=w_vol,
        w_sent=w_sent,
    ).normalized()

    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        # Load from DB existing tickers or fallback to default universe
        existing = [row[0] for row in db.query(StockMetricCache.ticker).all()]
        ticker_list = list(dict.fromkeys(existing + DEFAULT_UNIVERSE)) if existing else DEFAULT_UNIVERSE

    ranked = get_ranked_stocks(
        tickers=ticker_list,
        weights=weights,
        db=db,
        force_refresh=force_refresh,
    )

    return RankingsResponse(
        stocks=ranked,
        weights=weights,
        timestamp=datetime.datetime.utcnow().isoformat(),
        total_tracked=len(ranked),
    )


@app.get("/api/insider/{ticker}", response_model=InsiderDetailResponse)
def get_insider_filings(
    ticker: str,
    force_refresh: bool = Query(False, description="Force re-fetch from SEC EDGAR"),
    db: Session = Depends(get_db),
):
    """
    Fetches detailed SEC Form 4 insider transactions for a specific ticker.
    Highlights Transaction Code 'P' (open-market purchases) and Rule 10b5-1 status.
    """
    ticker_clean = ticker.strip().upper()
    if force_refresh:
        summary, items = fetch_and_cache_insider_data(ticker_clean, db)
    else:
        # Check if already cached in DB
        summary, items = fetch_and_cache_insider_data(ticker_clean, db)

    return InsiderDetailResponse(
        ticker=ticker_clean,
        summary=summary,
        transactions=items,
    )


@app.post("/api/ticker/{ticker}")
def add_ticker(
    ticker: str,
    db: Session = Depends(get_db),
):
    """Adds a custom stock ticker to the tracking universe and initiates metric caching."""
    ticker_clean = ticker.strip().upper()
    try:
        cached = get_or_update_stock_metric(ticker_clean, db, force_refresh=True)
        return {
            "status": "success",
            "message": f"Ticker {ticker_clean} added successfully.",
            "price": cached.current_price,
            "company_name": cached.company_name,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch data for ticker {ticker_clean}: {str(e)}",
        )


# Serve Static Files
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.api_route("/", methods=["GET", "HEAD"])
    @app.api_route("/dashboard", methods=["GET", "HEAD"])
    @app.api_route("/index.html", methods=["GET", "HEAD"])
    def serve_frontend_root():
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Frontend index.html not found. Please verify /frontend directory."}

    @app.get("/styles.css")
    def serve_css():
        return FileResponse(os.path.join(FRONTEND_DIR, "styles.css"))

    @app.get("/app.js")
    def serve_js():
        return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))


if __name__ == "__main__":
    import uvicorn
    import socket

    def find_available_port(preferred_port: int) -> int:
        for p in [preferred_port, 8001, 8080, 8888, 5000]:
            try:
                s = socket.socket()
                s.bind(('0.0.0.0', p))
                s.close()
                return p
            except OSError:
                continue
        return preferred_port

    preferred = int(os.getenv("PORT", settings.port))
    active_port = find_available_port(preferred)
    if active_port != preferred:
        print(f"\n[AlphaRadar] Notice: Port {preferred} is occupied by another service. Starting on port {active_port} instead.")
    print(f"\n[AlphaRadar] Dashboard running: http://localhost:{active_port}\n")
    uvicorn.run("backend.main:app", host=settings.host, port=active_port, reload=True)


