import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Database
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Finnhub
    api_key: str
    base_url: str
    tickers: list[str]

    # ETL
    interval_seconds: int
    history_days: int

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        raise ValueError(
            "FINNHUB_API_KEY is not set. Register for a free key at https://finnhub.io"
        )

    tickers_raw = os.getenv("STOCK_TICKERS", "AAPL,MSFT,GOOGL,AMZN,NVDA")
    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]

    return Settings(
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=os.getenv("POSTGRES_DB", "stocks_etl"),
        postgres_user=os.getenv("POSTGRES_USER", "etl_user"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
        api_key=api_key,
        base_url=os.getenv("FINNHUB_BASE_URL", "https://finnhub.io/api/v1"),
        tickers=tickers,
        interval_seconds=int(os.getenv("ETL_INTERVAL_SECONDS", "300")),
        history_days=int(os.getenv("HISTORY_DAYS", "30")),
    )
