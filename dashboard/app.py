import os
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Stock Market Dashboard",
    page_icon="📈",
    layout="wide",
)

# ── Database connection ───────────────────────────────────────────────────────

def _db_url() -> str:
    return (
        f"postgresql+psycopg2://"
        f"{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST', 'postgres')}:{os.getenv('POSTGRES_PORT', 5432)}"
        f"/{os.getenv('POSTGRES_DB')}"
    )


@st.cache_resource
def get_engine():
    return create_engine(_db_url(), pool_pre_ping=True, pool_size=3)


# ── Query helpers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_latest_quotes() -> pd.DataFrame:
    sql = text("""
        SELECT DISTINCT ON (ticker)
            ticker, current_price, open, high, low, prev_close,
            price_change, price_change_pct, fetched_at
        FROM stock_quotes
        ORDER BY ticker, fetched_at DESC
    """)
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


@st.cache_data(ttl=60)
def load_price_trend(ticker: str) -> pd.DataFrame:
    sql = text("""
        SELECT fetched_at, current_price
        FROM stock_quotes
        WHERE ticker = :ticker
        ORDER BY fetched_at ASC
    """)
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn, params={"ticker": ticker})
    return df


@st.cache_data(ttl=300)
def load_candles(ticker: str, days: int = 30) -> pd.DataFrame:
    sql = text("""
        SELECT date, open, high, low, close, volume
        FROM stock_candles
        WHERE ticker = :ticker
          AND date >= CURRENT_DATE - CAST(:days AS INT)
        ORDER BY date ASC
    """)
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn, params={"ticker": ticker, "days": days})
    return df


@st.cache_data(ttl=3600)
def load_profiles() -> pd.DataFrame:
    sql = text("SELECT ticker, name, exchange, industry, market_cap FROM company_profiles")
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("📈 Stock Market Dashboard")
st.caption("Data from Finnhub · auto-refreshes every 60s")

try:
    quotes = load_latest_quotes()
    profiles = load_profiles()
except Exception as e:
    st.error(f"Could not connect to database: {e}")
    st.stop()

if quotes.empty:
    st.warning("No data yet — the ETL pipeline may still be running its first fetch.")
    st.stop()

# Merge profiles for display
display = quotes.copy()
if not profiles.empty:
    display = display.merge(
        profiles[["ticker", "name", "industry"]], on="ticker", how="left"
    )
else:
    display["name"] = display["ticker"]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    selected_ticker = st.selectbox(
        "Select ticker for detail view",
        options=sorted(quotes["ticker"].tolist()),
    )
    candle_days = st.slider("Candle history (days)", 7, 90, 30)
    st.markdown("---")
    st.caption(f"Tracking {len(quotes)} tickers")
    if not quotes.empty:
        last_update = pd.to_datetime(quotes["fetched_at"]).max()
        st.caption(f"Last update: {last_update.strftime('%H:%M:%S UTC')}")

# ── KPI row ───────────────────────────────────────────────────────────────────
gainers = quotes[quotes["price_change_pct"] > 0]
losers  = quotes[quotes["price_change_pct"] < 0]

if not quotes["price_change_pct"].isna().all():
    top_gainer = quotes.loc[quotes["price_change_pct"].idxmax()]
    top_loser  = quotes.loc[quotes["price_change_pct"].idxmin()]
else:
    top_gainer = top_loser = None

col1, col2, col3, col4 = st.columns(4)
col1.metric("Tickers Tracked", len(quotes))
col2.metric("Gainers / Losers", f"{len(gainers)} / {len(losers)}")
if top_gainer is not None:
    col3.metric(
        f"Top Gainer: {top_gainer['ticker']}",
        f"${top_gainer['current_price']:.2f}",
        delta=f"{top_gainer['price_change_pct']:+.2f}%",
    )
if top_loser is not None:
    col4.metric(
        f"Top Loser: {top_loser['ticker']}",
        f"${top_loser['current_price']:.2f}",
        delta=f"{top_loser['price_change_pct']:+.2f}%",
        delta_color="inverse",
    )

st.divider()

# ── Market overview table ─────────────────────────────────────────────────────
st.subheader("Market Overview")
table_cols = ["ticker", "current_price", "price_change", "price_change_pct",
              "high", "low", "prev_close"]
if "name" in display.columns:
    table_cols = ["name"] + table_cols
if "industry" in display.columns:
    table_cols += ["industry"]

st.dataframe(
    display[table_cols].rename(columns={
        "ticker": "Ticker", "name": "Name", "current_price": "Price ($)",
        "price_change": "Change ($)", "price_change_pct": "Change (%)",
        "high": "High", "low": "Low", "prev_close": "Prev Close",
        "industry": "Industry",
    }).set_index("Ticker"),
    use_container_width=True,
)

st.divider()

# ── Price change bar chart ────────────────────────────────────────────────────
st.subheader("Price Change % — All Tickers")
bar_df = quotes.dropna(subset=["price_change_pct"]).sort_values("price_change_pct")
fig_bar = px.bar(
    bar_df,
    x="ticker",
    y="price_change_pct",
    color="price_change_pct",
    color_continuous_scale=["#d62728", "#aaaaaa", "#2ca02c"],
    color_continuous_midpoint=0,
    labels={"ticker": "Ticker", "price_change_pct": "Change (%)"},
    title="Daily Price Change %",
)
fig_bar.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45)
st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── Detail view for selected ticker ──────────────────────────────────────────
st.subheader(f"Detail: {selected_ticker}")

col_trend, col_candle = st.columns(2)

with col_trend:
    trend_df = load_price_trend(selected_ticker)
    if not trend_df.empty:
        fig_trend = px.line(
            trend_df,
            x="fetched_at",
            y="current_price",
            title=f"{selected_ticker} — Intraday Price Trend",
            labels={"fetched_at": "Time", "current_price": "Price ($)"},
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No intraday trend data yet.")

with col_candle:
    candle_df = load_candles(selected_ticker, candle_days)
    if not candle_df.empty:
        fig_candle = go.Figure(
            data=go.Candlestick(
                x=candle_df["date"],
                open=candle_df["open"],
                high=candle_df["high"],
                low=candle_df["low"],
                close=candle_df["close"],
                increasing_line_color="#2ca02c",
                decreasing_line_color="#d62728",
            )
        )
        fig_candle.update_layout(
            title=f"{selected_ticker} — Daily OHLCV ({candle_days}d)",
            xaxis_title="Date",
            yaxis_title="Price ($)",
            xaxis_rangeslider_visible=False,
        )
        st.plotly_chart(fig_candle, use_container_width=True)
    else:
        st.info("No candle data yet.")

# Volume chart
if not candle_df.empty:
    fig_vol = px.bar(
        candle_df,
        x="date",
        y="volume",
        title=f"{selected_ticker} — Daily Volume",
        labels={"date": "Date", "volume": "Volume"},
        color_discrete_sequence=["#1f77b4"],
    )
    st.plotly_chart(fig_vol, use_container_width=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(60)
st.rerun()
