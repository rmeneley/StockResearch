import logging
import datetime
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.models import InsiderTransactionModel, InsiderTransactionItem, InsiderSummary
from backend.config import settings

logger = logging.getLogger(__name__)

def parse_form4_filing(filing) -> List[Dict[str, Any]]:
    """
    Safely parses an edgartools Form 4 filing object.
    Strictly extracts Transaction Code 'P' (Open-market purchases) and checks 10b5-1 status.
    """
    extracted: List[Dict[str, Any]] = []
    try:
        f4 = filing.obj()
        if not f4:
            return extracted

        filing_date = str(getattr(filing, "filing_date", datetime.date.today().isoformat()))
        insider_name = str(getattr(f4, "insider_name", "") or "Insider")
        insider_title = str(getattr(f4, "position", "") or "Officer / Director")
        is_10b5_1 = bool(getattr(f4, "aff10b5_one", False))

        # Check footnotes if 10b5-1 was not directly affirmed
        if not is_10b5_1:
            footnotes = getattr(f4, "footnotes", {})
            if isinstance(footnotes, dict):
                for note_text in footnotes.values():
                    if "10b5-1" in str(note_text) or "10b51" in str(note_text):
                        is_10b5_1 = True
                        break

        # Check market_trades or common_stock_purchases/sales
        trades_df = getattr(f4, "market_trades", None)
        if trades_df is None or (hasattr(trades_df, "empty") and trades_df.empty):
            p_df = getattr(f4, "common_stock_purchases", None)
            s_df = getattr(f4, "common_stock_sales", None)
            dfs = [d for d in (p_df, s_df) if d is not None and not (hasattr(d, "empty") and d.empty)]
            if dfs:
                trades_df = pd.concat(dfs, ignore_index=True)

        if trades_df is not None and hasattr(trades_df, "iterrows") and not trades_df.empty:
            for _, row in trades_df.iterrows():
                code = str(row.get("Code", "") or row.get("transaction_code", "")).strip().upper()
                tx_type = str(row.get("TransactionType", "")).strip().lower()

                # Match Code 'P' (Purchase) or 'S' (Sale)
                is_buy = (code == "P" or "purchase" in tx_type)
                is_sell = (code == "S" or "sale" in tx_type)

                if is_buy or is_sell:
                    tx_code = "P" if is_buy else "S"
                    tx_type_str = "Purchase" if is_buy else "Sale"
                    shares = float(row.get("Shares", 0.0) or row.get("shares", 0.0) or 0.0)
                    price = float(row.get("Price", 0.0) or row.get("price", 0.0) or 0.0)
                    tx_date = str(row.get("Date", "") or filing_date)
                    total_val = float(shares * price) if price > 0 else 0.0

                    extracted.append({
                        "filing_date": tx_date,
                        "insider_name": insider_name,
                        "insider_title": insider_title,
                        "transaction_code": tx_code,
                        "transaction_type": tx_type_str,
                        "is_10b5_1": is_10b5_1,
                        "shares": shares,
                        "price_per_share": price,
                        "total_value": total_val,
                    })
    except Exception as e:
        logger.debug("Error parsing Form 4 filing: %s", e)

    return extracted


def fetch_and_cache_insider_data(
    ticker: str, db: Session, force_refresh: bool = False
) -> Tuple[InsiderSummary, List[InsiderTransactionItem]]:
    """
    Fetches recent Form 4 filings for ticker using edgartools.
    Extracts Code 'P' purchases and Code 'S' sales, caches to DB, and returns summary + items.
    """
    ticker_clean = ticker.strip().upper()

    # Check existing DB cache if not forcing refresh
    if not force_refresh:
        existing_count = db.query(InsiderTransactionModel).filter(InsiderTransactionModel.ticker == ticker_clean).count()
        if existing_count > 0:
            cached_recs = (
                db.query(InsiderTransactionModel)
                .filter(InsiderTransactionModel.ticker == ticker_clean)
                .order_by(InsiderTransactionModel.filing_date.desc())
                .limit(30)
                .all()
            )
            items: List[InsiderTransactionItem] = []
            buys_count = 0
            sells_count = 0
            total_buy_val = 0.0
            total_sell_val = 0.0
            unique_insiders = set()
            has_disc_buy = False
            has_disc_sell = False
            last_buy_date = None
            last_tx_date = None

            for r in cached_recs:
                is_buy = (r.transaction_code == "P")
                tx_type_str = "Purchase" if is_buy else "Sale"
                item = InsiderTransactionItem(
                    filing_date=r.filing_date,
                    insider_name=r.insider_name,
                    insider_title=r.insider_title,
                    transaction_code=r.transaction_code,
                    transaction_type=tx_type_str,
                    is_10b5_1=r.is_10b5_1,
                    shares=r.shares,
                    price_per_share=r.price_per_share,
                    total_value=r.total_value,
                )
                items.append(item)
                unique_insiders.add(r.insider_name)
                if not last_tx_date:
                    last_tx_date = r.filing_date

                if is_buy:
                    buys_count += 1
                    total_buy_val += r.total_value
                    if not r.is_10b5_1:
                        has_disc_buy = True
                    if not last_buy_date:
                        last_buy_date = r.filing_date
                else:
                    sells_count += 1
                    total_sell_val += r.total_value
                    if not r.is_10b5_1:
                        has_disc_sell = True

            summary = InsiderSummary(
                recent_buys_count=buys_count,
                total_buy_value=round(total_buy_val, 2),
                recent_sells_count=sells_count,
                total_sell_value=round(total_sell_val, 2),
                net_value=round(total_buy_val - total_sell_val, 2),
                unique_insiders_count=len(unique_insiders),
                has_discretionary_buy=has_disc_buy,
                has_discretionary_sell=has_disc_sell,
                last_buy_date=last_buy_date,
                last_transaction_date=last_tx_date,
            )
            return summary, items

    parsed_transactions: List[Dict[str, Any]] = []

    try:
        from edgar import Company
        company = Company(ticker_clean)
        filings = company.get_filings(form="4")
        if filings:
            recent_filings = filings[:15]
            for f in recent_filings:
                f_txs = parse_form4_filing(f)
                parsed_transactions.extend(f_txs)
    except ImportError:
        logger.warning("edgartools is not available; unable to query SEC EDGAR directly.")
    except Exception as e:
        logger.warning("Could not fetch EDGAR filings for %s: %s", ticker_clean, e)

    # Refresh SQLite cache for this ticker
    try:
        db.query(InsiderTransactionModel).filter(InsiderTransactionModel.ticker == ticker_clean).delete()
        for tx in parsed_transactions:
            rec = InsiderTransactionModel(
                ticker=ticker_clean,
                filing_date=tx["filing_date"],
                insider_name=tx["insider_name"],
                insider_title=tx["insider_title"],
                transaction_code=tx["transaction_code"],
                is_10b5_1=tx["is_10b5_1"],
                shares=tx["shares"],
                price_per_share=tx["price_per_share"],
                total_value=tx["total_value"],
            )
            db.add(rec)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to write insider transactions to DB for %s: %s", ticker_clean, e)

    # Read from DB to return
    cached_recs = (
        db.query(InsiderTransactionModel)
        .filter(InsiderTransactionModel.ticker == ticker_clean)
        .order_by(InsiderTransactionModel.filing_date.desc())
        .limit(30)
        .all()
    )

    items: List[InsiderTransactionItem] = []
    buys_count = 0
    sells_count = 0
    total_buy_val = 0.0
    total_sell_val = 0.0
    unique_insiders = set()
    has_disc_buy = False
    has_disc_sell = False
    last_buy_date = None
    last_tx_date = None

    for r in cached_recs:
        is_buy = (r.transaction_code == "P")
        tx_type_str = "Purchase" if is_buy else "Sale"
        item = InsiderTransactionItem(
            filing_date=r.filing_date,
            insider_name=r.insider_name,
            insider_title=r.insider_title,
            transaction_code=r.transaction_code,
            transaction_type=tx_type_str,
            is_10b5_1=r.is_10b5_1,
            shares=r.shares,
            price_per_share=r.price_per_share,
            total_value=r.total_value,
        )
        items.append(item)
        unique_insiders.add(r.insider_name)
        if not last_tx_date:
            last_tx_date = r.filing_date

        if is_buy:
            buys_count += 1
            total_buy_val += r.total_value
            if not r.is_10b5_1:
                has_disc_buy = True
            if not last_buy_date:
                last_buy_date = r.filing_date
        else:
            sells_count += 1
            total_sell_val += r.total_value
            if not r.is_10b5_1:
                has_disc_sell = True

    summary = InsiderSummary(
        recent_buys_count=buys_count,
        total_buy_value=round(total_buy_val, 2),
        recent_sells_count=sells_count,
        total_sell_value=round(total_sell_val, 2),
        net_value=round(total_buy_val - total_sell_val, 2),
        unique_insiders_count=len(unique_insiders),
        has_discretionary_buy=has_disc_buy,
        has_discretionary_sell=has_disc_sell,
        last_buy_date=last_buy_date,
        last_transaction_date=last_tx_date,
    )

    return summary, items
