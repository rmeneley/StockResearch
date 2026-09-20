import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.models import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_api_health(client):
    """Ensure the health endpoint returns status healthy with DB connectivity."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["db_connected"] is True
    assert data["sec_identity_set"] is True

def test_api_rankings_default(client):
    """Ensure rankings endpoint returns list of stocks and valid schema."""
    response = client.get("/api/rankings?tickers=AAPL,NVDA")
    assert response.status_code == 200
    data = response.json()
    assert "stocks" in data
    assert "weights" in data
    assert len(data["stocks"]) == 2
    
    first = data["stocks"][0]
    assert "ticker" in first
    assert "composite_score" in first
    assert -1.0 <= first["composite_score"] <= 1.0
    assert "rsi" in first
    assert "rvol" in first
    assert "insider" in first
    assert "sentiment" in first
    assert "next_earnings_date" in first
    assert "latest_news_time" in first
    assert "latest_news_title" in first

def test_api_rankings_custom_weights(client):
    """Ensure custom weights are reflected in rankings response."""
    response = client.get("/api/rankings?w_tech=0.7&w_insider=0.1&w_vol=0.1&w_sent=0.1&tickers=MSFT")
    assert response.status_code == 200
    data = response.json()
    assert data["weights"]["w_tech"] == 0.7
    assert len(data["stocks"]) == 1

def test_api_insider_detail(client):
    """Ensure insider transactions endpoint returns summary and transactions list."""
    response = client.get("/api/insider/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "summary" in data
    assert "transactions" in data
    assert isinstance(data["transactions"], list)


def test_api_news_detail(client):
    """Ensure news endpoint returns articles with required fields."""
    response = client.get("/api/news/AAPL?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "articles" in data
    assert isinstance(data["articles"], list)
    assert data["total_articles"] == len(data["articles"])
    if len(data["articles"]) > 0:
        first = data["articles"][0]
        assert "title" in first
        assert "publisher" in first
        assert "url" in first


