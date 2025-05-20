from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.sim import update_prices
from app.db import (
    is_market_running,
    start_market,
    stop_market,
    get_setting,
    set_setting,
)

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

from sqlalchemy import text
import pandas as pd
from app.db import engine
from app.sim import SIM_START_DATE
from datetime import datetime

@router.post("/advance-1")
async def advance_1_tick():
    hours = int(get_setting("hours_per_tick", 1))
    update_prices(ticks=1, hours_per_tick=hours)
    return {"status": "advanced", "ticks": 1, "hours_per_tick": hours}

@router.post("/advance-24")
async def advance_24_ticks():
    hours = int(get_setting("hours_per_tick", 1))
    update_prices(ticks=24, hours_per_tick=hours)
    return {"status": "advanced", "ticks": 24, "hours_per_tick": hours}

@router.post("/advance-30")
async def advance_30_ticks():
    hours = int(get_setting("hours_per_tick", 8))
    update_prices(ticks=30, hours_per_tick=hours)
    return {"status": "advanced", "ticks": 30, "hours_per_tick": hours}

@router.post("/advance-180")
async def advance_180_ticks():
    hours = int(get_setting("hours_per_tick", 24))
    update_prices(ticks=180, hours_per_tick=hours)
    return {"status": "advanced", "ticks": 180, "hours_per_tick": hours}

@router.post("/advance-365")
async def advance_365_ticks():
    hours = int(get_setting("hours_per_tick", 24))
    update_prices(ticks=365, hours_per_tick=hours)
    return {"status": "advanced", "ticks": 365, "hours_per_tick": hours}

@router.post("/start")
async def start_simulation():
    start_market()
    return {"status": "running"}

@router.post("/stop")
async def stop_simulation():
    stop_market()
    return {"status": "paused"}

@router.get("/status")
async def market_status():
    return {
        "market_running": is_market_running(),
        "sim_time": int(get_setting("sim_time", 0)),
        "sentiment": get_setting("market_sentiment", "Booming"),
        "tick_interval_sec": int(get_setting("tick_interval_sec", 60)),
    }

@router.post("/tick-hours")
async def update_tick_hours(hours: int = Form(...)):
    set_setting("hours_per_tick", str(hours))
    return {"status": "updated", "hours_per_tick": hours}

@router.get("/stocks", response_class=HTMLResponse)
async def show_stocks(request: Request):
    with engine.connect() as conn:
        stocks_df = pd.read_sql(text("SELECT Ticker, Name, Price, Volatility FROM stocks"), conn)
        history_df = pd.read_sql(text("SELECT * FROM price_history"), conn)

    history_df["Timestamp"] = pd.to_datetime(history_df["Timestamp"])
    latest_time = history_df["Timestamp"].max()

    def calc_return(delta: pd.Timedelta):
        ref_time = latest_time - delta
        ref_prices = history_df[history_df["Timestamp"] <= ref_time].sort_values("Timestamp").groupby("Ticker").last()["Price"]
        merged = stocks_df.join(ref_prices, on="Ticker", rsuffix="_past")
        return ((merged["Price"] - merged["Price_past"]) / merged["Price_past"]) * 100

    returns = {
        "1D": calc_return(pd.Timedelta(days=1)),
        "1W": calc_return(pd.Timedelta(weeks=1)),
        "1M": calc_return(pd.Timedelta(days=30)),
        "6M": calc_return(pd.Timedelta(days=182)),
        "1Y": calc_return(pd.Timedelta(days=365)),
        "All": calc_return(latest_time - SIM_START_DATE),
    }

    for key, series in returns.items():
        stocks_df[f"Change_{key}"] = series.round(2).fillna(0.0)

    stocks_df = stocks_df[["Ticker", "Name", "Price", "Volatility"] + [f"Change_{k}" for k in ["All", "1Y", "6M", "1M", "1W", "1D"]]]
    stocks_df = stocks_df.sort_values("Ticker")

    return templates.TemplateResponse("stocks.html", {
        "request": request,
        "stocks": stocks_df.to_dict(orient="records"),
        "chart_data": {"labels": [], "datasets": []}
    })

@router.get("/stock-data")
async def get_stock_data():
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT Ticker, Name, Price, Volatility FROM stocks"), conn)
        history_df = pd.read_sql(text("SELECT * FROM price_history"), conn)

    history_df["Timestamp"] = pd.to_datetime(history_df["Timestamp"])
    latest_time = history_df["Timestamp"].max()

    def calc_return(delta: pd.Timedelta):
        ref_time = latest_time - delta
        ref_prices = history_df[history_df["Timestamp"] <= ref_time].sort_values("Timestamp").groupby("Ticker").last()["Price"]
        merged = df.join(ref_prices, on="Ticker", rsuffix="_past")
        return ((merged["Price"] - merged["Price_past"]) / merged["Price_past"]) * 100

    returns = {
        "1D": calc_return(pd.Timedelta(days=1)),
        "1W": calc_return(pd.Timedelta(weeks=1)),
        "1M": calc_return(pd.Timedelta(days=30)),
        "6M": calc_return(pd.Timedelta(days=182)),
        "1Y": calc_return(pd.Timedelta(days=365)),
        "All": calc_return(latest_time - SIM_START_DATE),
    }

    for key, series in returns.items():
        df[f"Change_{key}"] = series.round(2).fillna(0.0)

    df = df[["Ticker", "Name", "Price", "Volatility"] + [f"Change_{k}" for k in ["All", "1Y", "6M", "1M", "1W", "1D"]]]
    df = df.sort_values("Ticker")

    return JSONResponse(content=df.to_dict(orient="records"))

@router.post("/admin/update_price")
async def update_stock_price(ticker: str = Form(...), new_price: float = Form(...)):
    try:
        with engine.connect() as conn:
            timestamp = datetime.utcnow()
            conn.execute(text("UPDATE stocks SET Price = :price WHERE Ticker = :ticker"),
                         {"price": new_price, "ticker": ticker})
            conn.execute(text("INSERT INTO price_history (Timestamp, Ticker, Price) VALUES (:ts, :ticker, :price)"),
                         {"ts": timestamp, "ticker": ticker, "price": new_price})
            conn.commit()
    except Exception as e:
        print("Price Update Error:", e)
    return RedirectResponse(url="/stocks", status_code=303)

@router.post("/admin/update_volatility")
async def update_volatility(ticker: str = Form(...), volatility: float = Form(...)):
    with engine.connect() as conn:
        conn.execute(text("UPDATE stocks SET Volatility = :vol WHERE Ticker = :ticker"),
                     {"vol": volatility, "ticker": ticker})
        conn.commit()
    return RedirectResponse(url="/stocks", status_code=303)

@router.post("/admin/update_drift")
async def update_drift(ticker: str = Form(...), drift: float = Form(...)):
    with engine.connect() as conn:
        conn.execute(text("UPDATE stocks SET DriftMultiplier = :drift WHERE Ticker = :ticker"),
                     {"drift": drift, "ticker": ticker})
        conn.commit()
    return RedirectResponse(url="/stocks", status_code=303)

@router.post("/admin/update_params")
async def update_market_parameters(rfr: float = Form(...), erp: float = Form(...), tick_interval: int = Form(...)):
    set_setting("risk_free_rate", str(rfr))
    set_setting("equity_risk_premium", str(erp))
    set_setting("tick_interval_sec", str(tick_interval))
    return RedirectResponse(url="/stocks", status_code=303)

@router.post("/admin/update_sentiment")
async def update_sentiment(sentiment: str = Form(...)):
    set_setting("market_sentiment", sentiment)
    return RedirectResponse(url="/stocks", status_code=303)

@router.get("/chart-data")
async def chart_data(t: str = "1M", mode: str = "price"):
    range_hours = {
        "1D": 24,
        "1W": 24 * 7,
        "1M": 24 * 30,
        "6M": 24 * 30 * 6,
        "1Y": 24 * 365
    }

    sim_time = int(get_setting("sim_time", 0))
    hours_per_tick = int(get_setting("hours_per_tick", 1))

    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text("SELECT Timestamp, Ticker, Price FROM price_history ORDER BY Timestamp ASC"),
                conn
            )

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])

        # 🟦 Skip cutoff filtering for "All"
        if t != "All":
            hours = range_hours.get(t, 24 * 30)
            cutoff_hours = sim_time * hours_per_tick - hours
            if cutoff_hours > 0:
                sim_start = pd.Timestamp("2200-01-01")
                cutoff_timestamp = sim_start + pd.Timedelta(hours=cutoff_hours)
                df = df[df["Timestamp"] >= cutoff_timestamp]

        # 🟨 Format labels by range
        if t == "1D":
            df["Label"] = df["Timestamp"].dt.strftime("%H:%M")
        elif t in ["1W", "1M"]:
            df["Label"] = df["Timestamp"].dt.strftime("%b %d")
        else:
            df["Label"] = df["Timestamp"].dt.strftime("%b %Y")

        datasets = []
        for ticker, group in df.groupby("Ticker"):
            prices = group["Price"].round(2).tolist()
            if mode == "percent" and len(prices) > 0:
                base = prices[0]
                prices = [((p - base) / base) * 100 for p in prices]

            datasets.append({
                "label": ticker,
                "data": group["Price"].round(2).tolist(),
                "borderColor": "#60A5FA",
                "fill": False,
            })

        labels = df["Label"].drop_duplicates().tolist()

        return JSONResponse({"labels": labels, "datasets": datasets})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/tools", response_class=HTMLResponse)
async def admin_tools(request: Request):
    return templates.TemplateResponse("tools.html", {"request": request})
