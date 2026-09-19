import os
import logging
from typing import Optional
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    class Settings(BaseSettings):
        sec_edgar_identity: str = "StockResearcher researcher@example.com"
        finnhub_api_key: str = ""
        database_url: str = "sqlite:///./stock_cache.db"
        cache_ttl_minutes: int = 60
        host: str = "0.0.0.0"
        port: int = 8000

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )
except ImportError:
    # Fallback to basic settings if pydantic_settings is not installed yet
    from pydantic import BaseModel
    class Settings(BaseModel):
        sec_edgar_identity: str = os.getenv("SEC_EDGAR_IDENTITY", "StockResearcher researcher@example.com")
        finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
        database_url: str = os.getenv("DATABASE_URL", "sqlite:///./stock_cache.db")
        cache_ttl_minutes: int = int(os.getenv("CACHE_TTL_MINUTES", "60"))
        host: str = os.getenv("HOST", "0.0.0.0")
        port: int = int(os.getenv("PORT", "8000"))

logger = logging.getLogger(__name__)

settings = Settings()

# Set Edgar local data directory inside workspace if not set
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if "EDGAR_LOCAL_DATA_DIR" not in os.environ:
    os.environ["EDGAR_LOCAL_DATA_DIR"] = os.path.join(_base_dir, ".edgar_data")
if "EDGAR_CACHE_DIR" not in os.environ:
    os.environ["EDGAR_CACHE_DIR"] = os.path.join(_base_dir, ".edgar_cache")

def init_edgar_identity():
    """Configures SEC EDGAR identity required by SEC fair-access policies."""
    try:
        from edgar import set_identity
        identity = settings.sec_edgar_identity.strip()
        if identity:
            set_identity(identity)
            logger.info("SEC EDGAR identity initialized successfully.")
    except ImportError:
        logger.warning("edgartools not installed yet; skipping set_identity.")
    except Exception as e:
        logger.warning("Failed to initialize SEC EDGAR identity: %s", e)

# Trigger initialization when config is loaded
init_edgar_identity()
