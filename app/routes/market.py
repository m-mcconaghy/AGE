from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return HTMLResponse("<h1>AGE Dashboard Coming Soon</h1>")
