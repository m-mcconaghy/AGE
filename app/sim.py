import pandas as pd
import numpy as np
from datetime import timedelta
from sqlalchemy import text
from app.db import engine, get_setting, set_setting

SIM_START_DATE = pd.Timestamp("2200-01-01")

def update_prices(ticks=1, hours_per_tick: int = 1):
    try:
        sim_time = int(get_setting("sim_time", 0))
        risk_free_rate = float(get_setting("risk_free_rate", 0.075))
        equity_risk_premium = float(get_setting("equity_risk_premium", 0.02))
        sentiment = get_setting("market_sentiment", "Booming")

        sentiment_multiplier = {
            "Bubbling": 0.03,
            "Booming": 0.01,
            "Stagnant": 0.005,
            "Receding": -0.02,
            "Depression": -0.05
        }
        mult = sentiment_multiplier.get(sentiment, 1.0)

        with engine.connect() as connection:
            df = pd.read_sql(text("SELECT * FROM stocks"), connection)

        tick_scale = hours_per_tick
        price_history_batch = []
        update_price_batch = []
        update_initial_price_batch = []

        for i in range(ticks):
            regime_multiplier = np.random.choice([1, 1.5], size=len(df), p=[0.95, 0.05])
            momentum = np.random.choice([1, -1], size=len(df))
            scaled_vol = df["Volatility"] * np.sqrt(tick_scale / 24)
            noise = np.random.normal(0, scaled_vol * regime_multiplier) * momentum

            drift_rate = (risk_free_rate + equity_risk_premium) * mult * df["DriftMultiplier"] / 24
            drift = np.clip(drift_rate * tick_scale * df["Price"], -0.002 * df["Price"], 0.002 * df["Price"])

            mean_reversion = 0.01 * (df["InitialPrice"] - df["Price"])
            shock_multipliers = np.random.choice([1.0, 0.95, 1.05], size=len(df), p=[0.998, 0.001, 0.001])
            base_price = df["Price"] * shock_multipliers

            new_price = base_price + noise * base_price + drift + mean_reversion
            new_price = np.clip(new_price, df["Price"] * 0.99, df["Price"] * 1.01)
            new_price = np.maximum(new_price, 0.01)

            df["Price"] = new_price

            current_sim_ticks = sim_time + i
            sim_timestamp = SIM_START_DATE + timedelta(hours=(current_sim_ticks * hours_per_tick))
            price_history_batch.extend([(sim_timestamp, t, p) for t, p in zip(df["Ticker"], df["Price"])])

            # adjust initial price only once per day of sim time
            if ((current_sim_ticks * hours_per_tick) % 24) == 0:
                new_initial_prices = df["InitialPrice"] * 1.00005
                update_initial_price_batch.extend(zip(new_initial_prices, df["Ticker"]))

        tmf_data = df[df["Ticker"] != "TMF"]
        tmf_price = float(np.average(tmf_data["Price"], weights=tmf_data["Volatility"]))
        df.loc[df["Ticker"] == "TMF", "Price"] = tmf_price

        update_price_batch = list(zip(df["Price"], df["Ticker"]))

        with engine.connect() as connection:
            connection.execute(
                text("INSERT INTO price_history (Timestamp, Ticker, Price) VALUES (:timestamp, :ticker, :price)"),
                [{"timestamp": ts, "ticker": tick, "price": p} for ts, tick, p in price_history_batch]
            )
            connection.execute(
                text("UPDATE stocks SET Price = :price WHERE Ticker = :ticker"),
                [{"price": price, "ticker": ticker} for price, ticker in update_price_batch]
            )
            if update_initial_price_batch:
                connection.execute(
                    text("UPDATE stocks SET InitialPrice = :initial_price WHERE Ticker = :ticker"),
                    [{"initial_price": ip, "ticker": tick} for ip, tick in update_initial_price_batch]
                )
            connection.commit()

        set_setting("sim_time", str(sim_time + ticks))

    except Exception as e:
        print(f"Error in update_prices: {e}")

