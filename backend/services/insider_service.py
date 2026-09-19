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
        
        # Determine reporting owner name & title
        owner_name = "Insider"
        owner_title = "Officer / Director"
        try:
            owners = getattr(f4, "reporting_owners", [])
            if owners and len(owners) > 0:
                first_owner = owners[0]
                owner_name = getattr(first_owner, "name", str(first_owner))
                rel = getattr(first_owner, "relationship", None)
                if rel:
                    owner_title = getattr(rel, "officer_title", "") or (
                        "Director" if getattr(rel, "is_director", False) else
                        "Officer" if getattr(rel, "is_officer", False) else
                        "Ten Percent Owner" if getattr(rel, "is_ten_percent_owner", False) else "Insider"
                    )
        except Exception:
            pass

        # Check for 10b5-1 affirmation at filing level or footnotes
        filing_is_10b5_1 = False
        try:
            affirmation = getattr(f4, "rule_10b5_1_affirmation", None) or getattr(f4, "rule10b51_affirmation", None)
            if affirmation is True or str(affirmation).strip() in ("1", "true", "True"):
                filing_is_10b5_1 = True
            
            # Also scan footnotes if available
            footnotes = getattr(f4, "footnotes", {})
            if isinstance(footnotes, dict):
                for note_text in footnotes.values():
                    if "10b5-1" in str(note_text) or "10b51" in str(note_text):
                        filing_is_10b5_1 = True
                        break
        except Exception:
            pass

        # Extract non-derivative transactions
        txs = getattr(f4, "non_derivative_transactions", [])
        if not txs:
            # Fallback to general transactions or dataframe if present
            txs = getattr(f4, "transactions", [])

        # Iterate transactions
        # If txs is a DataFrame
        if hasattr(txs, "iterrows"):
            for _, row in txs.iterrows():
                code = str(row.get("transaction_code", "") or row.get("TransactionCode", "")).strip().upper()
                if code == "P":
                    shares = float(row.get("shares", 0.0) or row.get("Shares", 0.0) or 0.0)
                    price = float(row.get("price", 0.0) or row.get("Price", 0.0) or 0.0)
                    total_val = float(row.get("total_value", 0.0) or (shares * price))
                    
                    row_10b5_1 = filing_is_10b5_1
                    if "10b5-1" in str(row).lower():
                        row_10b5_1 = True

                    extracted.append({
                        "filing_date": filing_date,
                        "insider_name": owner_name,
                        "insider_title": owner_title,
                        "transaction_code": "P",
                        "is_10b5_1": bool(row_10b5_1),
                        "shares": shares,
                        "price_per_share": price,
                        "total_value": total_val,
                    })
        elif isinstance(txs, (list, tuple)):
            for tx in txs:
                code = str(getattr(tx, "transaction_code", "") or getattr(tx, "security_transaction_code", "")).strip().upper()
                if code == "P":
                    shares = float(getattr(tx, "shares", 0.0) or getattr(tx, "transaction_shares", 0.0) or 0.0)
                    price = float(getattr(tx, "price", 0.0) or getattr(tx, "transaction_price_per_share", 0.0) or 0.0)
                    total_val = float(getattr(tx, "total_value", 0.0) or (shares * price))
                    
                    tx_10b5_1 = filing_is_10b5_1 or getattr(tx, "is_10b5_1", False)
                    extracted.append({
                        "filing_date": filing_date,
                        "insider_name": owner_name,
                        "insider_title": owner_title,
                        "transaction_code": "P",
                        "is_10b5_1": bool(tx_10b5_1),
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
    Strictly filters Transaction Code 'P', caches to DB, and returns summary + items.
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
                .limit(20)
                .all()
            )
            items: List[InsiderTransactionItem] = []
            total_val = 0.0
            unique_insiders = set()
            has_discretionary = False
            last_date = None

            for r in cached_recs:
                item = InsiderTransactionItem(
                    filing_date=r.filing_date,
                    insider_name=r.insider_name,
                    insider_title=r.insider_title,
                    transaction_code=r.transaction_code,
                    is_10b5_1=r.is_10b5_1,
                    shares=r.shares,
                    price_per_share=r.price_per_share,
                    total_value=r.total_value,
                )
                items.append(item)
                total_val += r.total_value
                unique_insiders.add(r.insider_name)
                if not r.is_10b5_1:
                    has_discretionary = True
                if not last_date:
                    last_date = r.filing_date

            summary = InsiderSummary(
                recent_buys_count=len(items),
                total_buy_value=round(total_val, 2),
                unique_insiders_count=len(unique_insiders),
                has_discretionary_buy=has_discretionary,
                last_buy_date=last_date,
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

    # If new transactions found, refresh SQLite cache for this ticker
    if parsed_transactions:
        try:
            # Clear old records for this ticker
            db.query(InsiderTransactionModel).filter(InsiderTransactionModel.ticker == ticker_clean).delete()
            for tx in parsed_transactions:
                rec = InsiderTransactionModel(
                    ticker=ticker_clean,
                    filing_date=tx["filing_date"],
                    insider_name=tx["insider_name"],
                    insider_title=tx["insider_title"],
                    transaction_code="P",
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
        .limit(20)
        .all()
    )

    items: List[InsiderTransactionItem] = []
    total_val = 0.0
    unique_insiders = set()
    has_discretionary = False
    last_date = None

    for r in cached_recs:
        item = InsiderTransactionItem(
            filing_date=r.filing_date,
            insider_name=r.insider_name,
            insider_title=r.insider_title,
            transaction_code=r.transaction_code,
            is_10b5_1=r.is_10b5_1,
            shares=r.shares,
            price_per_share=r.price_per_share,
            total_value=r.total_value,
        )
        items.append(item)
        total_val += r.total_value
        unique_insiders.add(r.insider_name)
        if not r.is_10b5_1:
            has_discretionary = True
        if not last_date:
            last_date = r.filing_date

    summary = InsiderSummary(
        recent_buys_count=len(items),
        total_buy_value=round(total_val, 2),
        unique_insiders_count=len(unique_insiders),
        has_discretionary_buy=has_discretionary,
        last_buy_date=last_date,
    )

    return summary, items
