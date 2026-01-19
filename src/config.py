"""Configuration management from environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SPOOL_DIR = DATA_DIR / "spool"
STATE_DB = DATA_DIR / "state.db"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
SPOOL_DIR.mkdir(exist_ok=True)


class Config:
    """Application configuration."""

    # DigiFactory
    BASE_URL: str = os.getenv("BASE_URL", "https://entrepreneur.digifactory.fr")
    LOGIN_URL: str = os.getenv("LOGIN_URL", f"{BASE_URL}/digi/com/login")
    USERNAME: str | None = os.getenv("USERNAME")
    PASSWORD: str | None = os.getenv("PASSWORD")
    SESSION_COOKIE: str | None = os.getenv("SESSION_COOKIE")

    # Scraper
    CONCURRENCY: int = int(os.getenv("CONCURRENCY", "20"))
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "1000"))
    RATE_PER_DOMAIN: float = float(os.getenv("RATE_PER_DOMAIN", "2.0"))
    TIMEOUT: int = int(os.getenv("TIMEOUT", "20"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "5"))

    # Supabase
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE: str | None = os.getenv("SUPABASE_SERVICE_ROLE")
    SUPABASE_TABLE: str = os.getenv("SUPABASE_TABLE", "digifactory_sales")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # API Security
    API_KEY: str | None = os.getenv("API_KEY")

    @classmethod
    def validate(cls, require_supabase: bool = True) -> None:
        """Validate required configuration."""
        errors = []
        if require_supabase:
            if not cls.SUPABASE_URL:
                errors.append("SUPABASE_URL is required")
            if not cls.SUPABASE_SERVICE_ROLE:
                errors.append("SUPABASE_SERVICE_ROLE is required")
        if not cls.USERNAME and not cls.SESSION_COOKIE:
            errors.append("Either USERNAME/PASSWORD or SESSION_COOKIE is required")
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")


config = Config()

