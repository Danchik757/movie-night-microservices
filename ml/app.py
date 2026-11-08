import json
import math
import os
from collections import defaultdict
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

config = json.loads(Path(__file__).with_name("config.json").read_text())
ARTIFACT = Path(os.environ.get("MODEL_PATH", config["artifact"]))
ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Movie Night ML")


class TrainData(BaseModel):
    movies: list[dict]
    ratings: list[dict]


class Choice(BaseModel):
    movieId: int
    rating: float = Field(ge=0.5, le=5)


class RecommendRequest(BaseModel):
    choices: list[Choice] = Field(min_length=1)
    limit: int = Field(10, ge=1, le=30)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/models")
def create_model():
    return {"model": "item-neighbors", "status": "ready-to-train"}


@app.post("/train")
def train(data: TrainData):
    if not data.movies or not data.ratings:
        raise HTTPException(400, "Сначала загрузите фильмы и оценки")
    by_user = defaultdict(dict)
    counts = defaultdict(int)
    sums = defaultdict(float)
    for row in data.ratings:
        user, movie, rating = int(row["userId"]), int(row["movieId"]), float(row["rating"])
        by_user[user][movie] = rating
        counts[movie] += 1
        sums[movie] += rating
    pairs = defaultdict(lambda: [0.0, 0])
    for user_ratings in by_user.values():
        liked = sorted((movie, rating) for movie, rating in user_ratings.items() if rating >= 3.5)
        for i, (left, lr) in enumerate(liked):
            for right, rr in liked[i + 1:]:
                pair = pairs[(left, right)]
                pair[0] += (lr - 2.5) * (rr - 2.5)
                pair[1] += 1
    neighbors = defaultdict(list)
    for (left, right), (weight, shared) in pairs.items():
        if shared < 2:
            continue
        score = weight / math.sqrt(counts[left] * counts[right])
        neighbors[left].append((right, score))
        neighbors[right].append((left, score))
    model = {
        "movies": {str(x["movieId"]): {"title": x["title"], "genres": x["genres"].split("|")} for x in data.movies},
        "neighbors": {str(k): sorted(v, key=lambda x: x[1], reverse=True)[:100] for k, v in neighbors.items()},
        "popular": sorted(((k, sums[k] / counts[k], counts[k]) for k in counts if counts[k] >= 5), key=lambda x: x[1] * math.log1p(x[2]), reverse=True)[:500],
        "ratings_count": len(data.ratings),
    }
    temp = ARTIFACT.with_suffix(".tmp")
    temp.write_text(json.dumps(model), encoding="utf-8")
    temp.replace(ARTIFACT)
    return {"status": "trained", "movies": len(model["movies"]), "ratings": len(data.ratings)}


@app.get("/summary")
def summary():
    if not ARTIFACT.exists():
        return {"status": "untrained"}
    model = json.loads(ARTIFACT.read_text())
    return {"status": "trained", "movies": len(model["movies"]), "ratings": model["ratings_count"], "method": "item-item co-occurrence with genre fallback"}


@app.post("/recommend")
def recommend(request: RecommendRequest):
    if not ARTIFACT.exists():
        raise HTTPException(409, "Сначала обучите модель")
    model = json.loads(ARTIFACT.read_text())
    selected = {str(x.movieId) for x in request.choices}
    scores = defaultdict(float)
    liked_genres = set()
    for choice in request.choices:
        if str(choice.movieId) not in model["movies"]:
            raise HTTPException(404, f"Фильм {choice.movieId} не найден")
        if choice.rating < 3.5:
            continue
        liked_genres.update(model["movies"][str(choice.movieId)]["genres"])
        for movie_id, similarity in model["neighbors"].get(str(choice.movieId), []):
            scores[str(movie_id)] += similarity * (choice.rating - 2.5)
    for movie_id, average, count in model["popular"]:
        item = model["movies"].get(str(movie_id))
        if item:
            overlap = len(liked_genres.intersection(item["genres"]))
            scores[str(movie_id)] += 0.08 * overlap + 0.001 * average * math.log1p(count)
    result = []
    for movie_id in sorted(scores, key=scores.get, reverse=True):
        if movie_id not in selected and movie_id in model["movies"]:
            result.append({"movieId": int(movie_id), **model["movies"][movie_id], "score": round(scores[movie_id], 3)})
        if len(result) >= request.limit:
            break
    return {"items": result}
