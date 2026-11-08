import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query

config = json.loads(Path(__file__).with_name("config.json").read_text())
DATA = Path(__file__).parent / "data"
app = FastAPI(title="Movie Night Collector")


def rows(kind):
    if kind not in ("movies", "ratings"):
        raise HTTPException(404, "Неизвестный набор данных")
    with (DATA / f"{kind}.csv").open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/batch/{kind}")
def batch(kind: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)):
    records = rows(kind)
    result = {"kind": kind, "offset": offset, "total": len(records), "items": records[offset:offset + limit]}
    log = Path(os.environ.get("COLLECTOR_LOG", "/data/downloads.jsonl"))
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stream:
        stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "kind": kind, "offset": offset, "count": len(result["items"])}) + "\n")
    return result


@app.get("/summary")
def summary():
    return {kind: len(rows(kind)) for kind in ("movies", "ratings")}
