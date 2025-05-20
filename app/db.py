import os
from dotenv import load_dotenv

# Force dotenv to load from root manually
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(dotenv_path=env_path)

import numpy as np  # ✅ add this
from sqlalchemy import create_engine, text

DATABASE_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ... rest of your code


def get_setting(key: str, default=None):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT value FROM market_status WHERE `key` = :key"), {"key": key}).fetchone()
        return result[0] if result else default

def set_setting(key: str, value: str):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO market_status (`key`, `value`) VALUES (:key, :value)
            ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)
        """), {"key": key, "value": value})
        conn.commit()

def initialize_market_status_defaults():
    defaults = {
        "sim_time": "0",
        "risk_free_rate": "0.075",
        "equity_risk_premium": "0.02",
        "market_sentiment": "Booming",
        "market_running": "true",
        "tick_interval_sec": "150",
        "hours_per_tick": "1"
    }
    
    with engine.connect() as conn:
        # ✅ Ensure table exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS market_status (
                `key` VARCHAR(255) PRIMARY KEY,
                `value` VARCHAR(255)
            )
        """))

        # Insert default values
        for key, value in defaults.items():
            conn.execute(text("""
                INSERT INTO market_status (`key`, `value`)
                VALUES (:key, :value)
                ON DUPLICATE KEY UPDATE `value` = `value`
            """), {"key": key, "value": value})

        conn.commit()

def initialize_stocks():
    base_tickers = ["DTF", "GMG", "USF", "TTT", "GFU", "IWI", "EE", "NEC", "ARC", "SOL",
                    "AWE", "ORB", "QNT", "AGX", "LCO", "FMC", "SYX", "VLT", "EXR", "CRB"]
    names = ["Directorate Tech Fund", "Galactic Mining Guild", "Universal Services Fund", "The Textile Team",
             "Galactic Farmers Union", "Imperial Weapons Industry", "Epsilon Exchange", "Nebular Energy Consortium",
             "Asteroid Resources Collective", "Solar Operations League", "Algalterian Water Exchange",
             "Orbital Rare Biotech", "Quantum Nexus Trust", "Agricultural Exports Guild", "Lunar Construction Outfit",
             "Frontier Medical Consortium", "Syphonix Energy Systems", "Veltrax AI Logistics", "Exorium Rare Elements",
             "Crystalline Banking Network"]
    initial_prices = [105.0, 95.0, 87.5, 76.0, 82.0, 132.0, 151.0, 91.0, 87.5, 102.0,
                      78.0, 113.0, 139.0, 84.0, 62.0, 144.0, 193.0, 119.0, 221.0, 68.0]
    volatility = [0.04, 0.035, 0.015, 0.02, 0.025, 0.03, 0.06, 0.018, 0.025, 0.02,
                  0.015, 0.045, 0.03, 0.017, 0.023, 0.014, 0.055, 0.027, 0.06, 0.018]

    with engine.connect() as conn:
        # Create stocks table if it doesn't exist
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stocks (
                Ticker VARCHAR(10) PRIMARY KEY,
                Name VARCHAR(255),
                Price DOUBLE,
                Volatility DOUBLE,
                InitialPrice DOUBLE,
                DriftMultiplier DOUBLE DEFAULT 1.0
            )
        """))

        # ✅ Create price_history table if it doesn't exist
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS price_history (
                Timestamp DATETIME,
                Ticker VARCHAR(10),
                Price DOUBLE
            )
        """))

        # Skip re-initialization if stock data already exists
        result = conn.execute(text("SELECT COUNT(*) FROM stocks")).scalar_one()
        if result > 0:
            return

        # Insert base stocks
        for i in range(len(base_tickers)):
            conn.execute(text("""
                INSERT INTO stocks (Ticker, Name, Price, Volatility, InitialPrice)
                VALUES (:ticker, :name, :price, :volatility, :initial_price)
            """), {
                "ticker": base_tickers[i],
                "name": names[i],
                "price": initial_prices[i],
                "volatility": volatility[i],
                "initial_price": initial_prices[i]
            })

        # Insert Total Market Fund (TMF)
        tmf_price = float(np.average(initial_prices, weights=initial_prices))
        tmf_vol = float(np.average(volatility, weights=initial_prices))
        conn.execute(text("""
            INSERT INTO stocks (Ticker, Name, Price, Volatility, InitialPrice)
            VALUES (:ticker, :name, :price, :volatility, :initial_price)
        """), {
            "ticker": "TMF",
            "name": "Total Market Fund",
            "price": tmf_price,
            "volatility": tmf_vol,
            "initial_price": tmf_price
        })

        conn.commit()
        
def is_market_running() -> bool:
    return get_setting("market_running", "false").lower() == "true"

def start_market():
    set_setting("market_running", "true")

def stop_market():
    set_setting("market_running", "false")
