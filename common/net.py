import os
import httpx
from fastapi import HTTPException


async def request(method, base, path, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request(method, base + path, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, exc.response.text[:500]) from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, f"Сервис недоступен: {exc}") from exc


def url(name):
    return os.environ.get(name.upper() + "_URL", "http://" + name + ":8000")
