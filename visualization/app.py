import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

config = json.loads(Path(__file__).with_name("config.json").read_text())
app = FastAPI(title="Movie Night Visualization")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    return Path(__file__).with_name("index.html").read_text(encoding="utf-8")
