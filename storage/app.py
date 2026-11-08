import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

config = json.loads(Path(__file__).with_name("config.json").read_text())
DB = os.environ.get("STORAGE_DB", config["database"])
Path(DB).parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Movie Night Storage")


@contextmanager
def connection():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


with connection() as db:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS movies (movie_id INTEGER PRIMARY KEY, title TEXT NOT NULL, genres TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ratings (user_id INTEGER, movie_id INTEGER, rating REAL, PRIMARY KEY(user_id,movie_id));
    CREATE INDEX IF NOT EXISTS ratings_movie ON ratings(movie_id);
    """)


class Movie(BaseModel):
    movieId: int
    title: str
    genres: str


class Rating(BaseModel):
    userId: int
    movieId: int
    rating: float = Field(ge=0.5, le=5)


class Batch(BaseModel):
    items: list[dict]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/movies/batch")
def add_movies(batch: Batch):
    try:
        items = [Movie(**item) for item in batch.items]
        with connection() as db:
            db.executemany("INSERT OR REPLACE INTO movies VALUES (?,?,?)", [(x.movieId, x.title, x.genres) for x in items])
        return {"saved": len(items)}
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/ratings/batch")
def add_ratings(batch: Batch):
    try:
        items = [Rating(**item) for item in batch.items]
        with connection() as db:
            db.executemany("INSERT OR REPLACE INTO ratings VALUES (?,?,?)", [(x.userId, x.movieId, x.rating) for x in items])
        return {"saved": len(items)}
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/movies")
def movies(q: str = "", limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    with connection() as db:
        records = db.execute("SELECT movie_id AS movieId,title,genres FROM movies WHERE title LIKE ? ORDER BY title LIMIT ? OFFSET ?", (f"%{q}%", limit, offset)).fetchall()
        return {"items": [dict(row) for row in records]}


@app.get("/movies/{movie_id}")
def movie(movie_id: int):
    with connection() as db:
        row = db.execute("SELECT movie_id AS movieId,title,genres FROM movies WHERE movie_id=?", (movie_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Фильм не найден")
    return dict(row)


@app.delete("/movies/{movie_id}")
def delete_movie(movie_id: int):
    with connection() as db:
        count = db.execute("DELETE FROM movies WHERE movie_id=?", (movie_id,)).rowcount
    if not count:
        raise HTTPException(404, "Фильм не найден")
    return {"deleted": movie_id}


@app.put("/movies/{movie_id}")
def update_movie(movie_id: int, item: Movie):
    if item.movieId != movie_id:
        raise HTTPException(400, "movieId не совпадает с URL")
    return add_movies(Batch(items=[item.model_dump()]))


@app.post("/ratings")
def add_rating(item: Rating):
    with connection() as db:
        if not db.execute("SELECT 1 FROM movies WHERE movie_id=?", (item.movieId,)).fetchone():
            raise HTTPException(404, "Фильм не найден")
    return add_ratings(Batch(items=[item.model_dump()]))


@app.get("/ratings/{user_id}")
def user_ratings(user_id: int):
    with connection() as db:
        rows = db.execute("SELECT user_id AS userId,movie_id AS movieId,rating FROM ratings WHERE user_id=?", (user_id,)).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.get("/export")
def export():
    with connection() as db:
        movies = [dict(row) for row in db.execute("SELECT movie_id AS movieId,title,genres FROM movies")]
        ratings = [dict(row) for row in db.execute("SELECT user_id AS userId,movie_id AS movieId,rating FROM ratings")]
    return {"movies": movies, "ratings": ratings}


@app.get("/stats")
def stats():
    with connection() as db:
        return {"movies": db.execute("SELECT COUNT(*) FROM movies").fetchone()[0], "ratings": db.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]}
