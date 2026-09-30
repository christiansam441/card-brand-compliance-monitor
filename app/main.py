from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Card Brand Compliance Monitor")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@lru_cache(maxsize=1)
def _data():
    return analysis.load_data()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/portfolio")
def api_portfolio():
    return analysis.portfolio(_data())


@app.get("/api/merchants/{merchant_id}")
def api_merchant(merchant_id: str):
    detail = analysis.merchant_detail(_data(), merchant_id.upper())
    if detail is None:
        raise HTTPException(status_code=404, detail="Unknown merchant")
    return detail
