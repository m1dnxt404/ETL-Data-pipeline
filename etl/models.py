from sqlalchemy import BigInteger, Column, Date, Integer, Numeric, String, Text
from sqlalchemy import DateTime, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class StockQuote(Base):
    __tablename__ = "stock_quotes"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    ticker           = Column(String(20),  nullable=False)
    current_price    = Column(Numeric(12, 4))
    open             = Column(Numeric(12, 4))
    high             = Column(Numeric(12, 4))
    low              = Column(Numeric(12, 4))
    prev_close       = Column(Numeric(12, 4))
    price_change     = Column(Numeric(12, 4))
    price_change_pct = Column(Numeric(8, 4))
    fetched_at       = Column(DateTime(timezone=True), nullable=False,
                              server_default=text("NOW()"))


class StockCandle(Base):
    __tablename__ = "stock_candles"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    ticker     = Column(String(20), nullable=False)
    date       = Column(Date, nullable=False)
    open       = Column(Numeric(12, 4))
    high       = Column(Numeric(12, 4))
    low        = Column(Numeric(12, 4))
    close      = Column(Numeric(12, 4))
    volume     = Column(BigInteger)
    fetched_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=text("NOW()"))


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    ticker     = Column(String(20),  primary_key=True)
    name       = Column(String(200))
    exchange   = Column(String(50))
    industry   = Column(String(100))
    market_cap = Column(Numeric(20, 2))
    shares_out = Column(BigInteger)
    logo_url   = Column(Text)
    website    = Column(Text)
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=text("NOW()"))
