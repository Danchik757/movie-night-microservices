import json
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from common.net import request, url

config = json.loads(Path(__file__).with_name("config.json").read_text())
app = FastAPI(title="Movie Night API Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


class Choice(BaseModel):
    movieId: int
    rating: float = Field(ge=0.5, le=5)


class RecommendInput(BaseModel):
    choices: list[Choice] = Field(min_length=1)
    limit: int = Field(10, ge=1, le=30)


@app.get("/health")
async def health():
    result = {}
    for service in ("collector", "storage", "ml"):
        try:
            result[service] = await request("GET", url(service), "/health")
        except Exception as exc:
            result[service] = {"status": "error", "detail": str(exc)}
    return result


@app.get("/status")
async def status():
    return {"source": await request("GET", url("collector"), "/summary"), "storage": await request("GET", url("storage"), "/stats"), "model": await request("GET", url("ml"), "/summary")}


@app.post("/import/{kind}")
async def import_batch(kind: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)):
    batch = await request("GET", url("collector"), f"/batch/{kind}", params={"offset": offset, "limit": limit})
    saved = await request("POST", url("storage"), f"/{kind}/batch", json={"items": batch["items"]})
    return {"kind": kind, "offset": offset, "total": batch["total"], **saved}


@app.post("/import-all")
async def import_all():
    result = {}
    for kind in ("movies", "ratings"):
        first = await request("GET", url("collector"), f"/batch/{kind}", params={"offset": 0, "limit": 2000})
        total_saved = 0
        for offset in range(0, first["total"], 2000):
            batch = first if offset == 0 else await request("GET", url("collector"), f"/batch/{kind}", params={"offset": offset, "limit": 2000})
            saved = await request("POST", url("storage"), f"/{kind}/batch", json={"items": batch["items"]})
            total_saved += saved["saved"]
        result[kind] = total_saved
    return result


@app.get("/movies")
async def movies(q: str = "", limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await request("GET", url("storage"), "/movies", params={"q": q, "limit": limit, "offset": offset})


@app.post("/train")
async def train():
    data = await request("GET", url("storage"), "/export")
    return await request("POST", url("ml"), "/train", json=data)


@app.post("/recommend")
async def recommend(payload: RecommendInput):
    return await request("POST", url("ml"), "/recommend", json=payload.model_dump())
