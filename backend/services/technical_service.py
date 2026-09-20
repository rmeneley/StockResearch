import logging
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def compute_rsi_series(series: pd.Series, period: int = 14) -> pd.Series:
    """Native pandas calculation of RSI using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def compute_technicals_from_df(df: pd.DataFrame) -> Dict[str, float]:
    """
    Computes technical indicators from a DataFrame containing Close and Volume.
    Uses pandas_ta if available, with automatic fallback to pure pandas.
    """
    if len(df) < 20:
        raise ValueError(f"Insufficient history data: {len(df)} rows found, at least 20 required.")

    close = df["Close"]
    volume = df["Volume"]

    rsi_val = 50.0
    ema20_val = float(close.iloc[-1])
    ema50_val = float(close.iloc[-1])
    macd_line = 0.0
    macd_sig = 0.0
    macd_hist = 0.0

    # Try ta or pandas-ta first
    used_lib = False
    try:
        from ta.momentum import RSIIndicator
        from ta.trend import EMAIndicator, MACD
        rsi_val = float(RSIIndicator(close=close, window=14).rsi().iloc[-1])
        ema20_val = float(EMAIndicator(close=close, window=20).ema_indicator().iloc[-1])
        if len(close) >= 50:
            ema50_val = float(EMAIndicator(close=close, window=50).ema_indicator().iloc[-1])
        else:
            ema50_val = ema20_val
        macd_obj = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = float(macd_obj.macd().iloc[-1])
        macd_sig = float(macd_obj.macd_signal().iloc[-1])
        macd_hist = float(macd_obj.macd_diff().iloc[-1])
        used_lib = True
    except Exception as e:
        logger.debug("ta library calculation encountered %s; checking pandas-ta or pure pandas", e)

    if not used_lib:
        try:
            import pandas_ta as ta
            ta_df = df.copy()
            ta_df.ta.rsi(length=14, append=True)
            ta_df.ta.ema(length=20, append=True)
            if len(df) >= 50:
                ta_df.ta.ema(length=50, append=True)
            ta_df.ta.macd(fast=12, slow=26, signal=9, append=True)

            for col in ta_df.columns:
                col_str = str(col)
                if col_str.startswith("RSI_14"):
                    rsi_val = float(ta_df[col].iloc[-1])
                elif col_str.startswith("EMA_20"):
                    ema20_val = float(ta_df[col].iloc[-1])
                elif col_str.startswith("EMA_50"):
                    ema50_val = float(ta_df[col].iloc[-1])
                elif col_str.startswith("MACD_12_26_9"):
                    macd_line = float(ta_df[col].iloc[-1])
                elif col_str.startswith("MACDs_12_26_9"):
                    macd_sig = float(ta_df[col].iloc[-1])
                elif col_str.startswith("MACDh_12_26_9"):
                    macd_hist = float(ta_df[col].iloc[-1])
            used_lib = True
        except Exception:
            pass

    # Pure pandas fallback if external indicator libraries were not used or produced NaNs
    if not used_lib or np.isnan(rsi_val):
        rsi_series = compute_rsi_series(close, 14)
        rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

        ema20_s = close.ewm(span=20, adjust=False).mean()
        ema20_val = float(ema20_s.iloc[-1])

        ema50_s = close.ewm(span=50, adjust=False).mean() if len(close) >= 50 else ema20_s
        ema50_val = float(ema50_s.iloc[-1])

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_series = ema12 - ema26
        signal_series = macd_series.ewm(span=9, adjust=False).mean()
        hist_series = macd_series - signal_series

        macd_line = float(macd_series.iloc[-1])
        macd_sig = float(signal_series.iloc[-1])
        macd_hist = float(hist_series.iloc[-1])

    # Clean NaNs
    rsi_val = 50.0 if np.isnan(rsi_val) else float(rsi_val)
    ema20_val = float(close.iloc[-1]) if np.isnan(ema20_val) else float(ema20_val)
    ema50_val = float(close.iloc[-1]) if np.isnan(ema50_val) else float(ema50_val)
    macd_hist = 0.0 if np.isnan(macd_hist) else float(macd_hist)

    # Calculate RVOL (Relative Volume: Current Day Volume / 20-day SMA of Volume)
    vol_window = min(20, len(volume))
    avg_vol_20 = volume.iloc[-vol_window:].mean()
    current_vol = float(volume.iloc[-1])

    if avg_vol_20 > 0:
        rvol = current_vol / avg_vol_20
    else:
        rvol = 1.0

    return {
        "rsi": round(rsi_val, 2),
        "ema_20": round(ema20_val, 2),
        "ema_50": round(ema50_val, 2),
        "macd_line": round(macd_line, 4),
        "macd_signal": round(macd_sig, 4),
        "macd_hist": round(macd_hist, 4),
        "rvol": round(rvol, 2),
    }


def fetch_technical_data(ticker: str) -> Dict[str, Any]:
    """
    Fetches market data for ticker via yfinance and computes indicators.
    Returns dictionary with current price, 1-day change %, and indicators.
    """
    ticker_clean = ticker.strip().upper()
    try:
        import yfinance as yf
        t = yf.Ticker(ticker_clean)
        # Fetch 6 months of daily data to ensure 50-day EMA and 20-day RVOL are accurate
        df = t.history(period="6mo", interval="1d")

        if df.empty or len(df) < 5:
            logger.warning("No price data returned by yfinance for %s", ticker_clean)
            return get_default_technical_data(ticker_clean)

        # Company name
        company_name = ticker_clean
        try:
            info = t.info
            company_name = info.get("shortName") or info.get("longName") or ticker_clean
        except Exception:
            pass

        # Next earnings date from calendar
        next_earnings_date = None
        try:
            cal = t.calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                ed = cal["Earnings Date"]
                if isinstance(ed, list) and len(ed) > 0:
                    next_earnings_date = str(ed[0])
                elif ed:
                    next_earnings_date = str(ed)
        except Exception:
            pass

        latest_close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else latest_close
        price_change_pct = ((latest_close - prev_close) / prev_close) * 100.0 if prev_close > 0 else 0.0

        indicators = compute_technicals_from_df(df)

        return {
            "ticker": ticker_clean,
            "company_name": company_name,
            "current_price": round(latest_close, 2),
            "price_change_pct": round(price_change_pct, 2),
            "next_earnings_date": next_earnings_date,
            **indicators
        }
    except Exception as e:
        logger.error("Error fetching technical data for %s: %s", ticker_clean, e)
        return get_default_technical_data(ticker_clean)


def get_default_technical_data(ticker: str) -> Dict[str, Any]:
    """Fallback defaults for ticker when external API is unavailable."""
    return {
        "ticker": ticker.upper(),
        "company_name": ticker.upper(),
        "current_price": 100.0,
        "price_change_pct": 0.0,
        "next_earnings_date": None,
        "rsi": 50.0,
        "ema_20": 100.0,
        "ema_50": 100.0,
        "macd_line": 0.0,
        "macd_signal": 0.0,
        "macd_hist": 0.0,
        "rvol": 1.0,
    }

