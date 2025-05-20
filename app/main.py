from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import asyncio

from app.routes import market

from app.db import (
    initialize_market_status_defaults,
    initialize_stocks,
    is_market_running,
    get_setting,
)
from app.sim import update_prices

# --- Database Bootstrap ---
initialize_market_status_defaults()
initialize_stocks()

# --- Background Tick Engine ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    async def auto_tick():
        while True:
            if is_market_running():
                interval = int(get_setting("tick_interval_sec", 150))
                hours_per_tick = int(get_setting("hours_per_tick", 1))
                update_prices(ticks=1, hours_per_tick=hours_per_tick)
                print("✅ Auto-ticked 1 step.")
                await asyncio.sleep(interval)
            else:
                await asyncio.sleep(2)

    asyncio.create_task(auto_tick())
    yield  # FastAPI runs after this

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)
app.include_router(market.router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
