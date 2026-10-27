import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.analytics import analytics
from app.chat import answer, narrate_analytics, narrate_brief, narrate_rice
from app.command import command_center
from app.map_intel import map_intel
from app.db import connect
from app.engine import recompute
from app.rice import rice
from app.reports import (
    algorithms,
    briefing,
    dataset_status,
    line_features,
    map_features,
    place_detail,
    priority,
    threat_list,
)
from app.seed import ensure_seeded, password_hash

log = logging.getLogger("cropwatch")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for attempt in range(30):
        try:
            ensure_seeded()
            break
        except Exception as exc:
            log.warning("database not ready (%s), retry %s", exc, attempt)
            await asyncio.sleep(2)
    else:
        log.error("database seed failed")
    task = asyncio.create_task(_refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="CROPWATCH", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginBody(BaseModel):
    username: str
    password: str


class NoteBody(BaseModel):
    place_slug: str
    body: str = Field(min_length=3, max_length=2000)


class ChatBody(BaseModel):
    message: str = Field(min_length=2, max_length=1000)
    threat_id: str
    season: str
    forecast_day: int = Field(ge=0, le=6)


class NoteReadBody(BaseModel):
    body: str = Field(min_length=3, max_length=2000)


class ImageBody(BaseModel):
    media_type: str
    data_base64: str = Field(min_length=16, max_length=8_000_000)


class SelectionBody(BaseModel):
    threat_id: str
    season: str
    forecast_day: int = Field(ge=0, le=6)


def _user(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in with a demo account.")
    token = authorization.split(" ", 1)[1].strip()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.municipality_slug, u.display_name
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = %s
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    return row


def _selection(threat_id: str, season: str, forecast_day: int) -> tuple[str, str, int]:
    known = {item["id"] for item in threat_list()}
    if threat_id not in known:
        raise HTTPException(status_code=400, detail="Unknown threat.")
    if season not in ("wet", "dry"):
        raise HTTPException(status_code=400, detail="Season must be wet or dry.")
    if not 0 <= forecast_day <= 6:
        raise HTTPException(status_code=400, detail="Forecast day must be 0 to 6.")
    return threat_id, season, forecast_day


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/login")
def login(body: LoginBody):
    digest = password_hash(body.password)
    with connect() as conn:
        user = conn.execute(
            "SELECT id, username, role, municipality_slug, display_name FROM users WHERE username = %s AND password_hash = %s",
            (body.username.strip(), digest),
        ).fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Unknown demo account.")
        token = secrets.token_urlsafe(24)
        conn.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, user["id"]))
        conn.commit()
    return {"token": token, "user": dict(user)}


@app.get("/api/threats")
def threats(authorization: str | None = Header(default=None)):
    _user(authorization)
    return threat_list()


@app.get("/api/status")
def status(authorization: str | None = Header(default=None)):
    _user(authorization)
    return dataset_status()


@app.get("/api/layer")
def layer_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    from app.layer import situation_layer

    return situation_layer(threat_id, season, forecast_day, user["role"], scope)


@app.post("/api/notes/read")
def read_note_route(body: NoteReadBody, authorization: str | None = Header(default=None)):
    _user(authorization)
    from app.layer import read_note

    return read_note(body.body)


@app.post("/api/field-image")
def field_image_route(body: ImageBody, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="The guest account cannot submit a field photo.")
    from app.layer import review_image

    return review_image(body.media_type, body.data_base64)


@app.get("/api/command")
def command_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    return command_center(threat_id, season, forecast_day, user["role"], scope)


@app.post("/api/command/narrate")
def command_narrate_route(body: SelectionBody, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(body.threat_id, body.season, body.forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    record = command_center(threat_id, season, forecast_day, user["role"], scope)
    return narrate_brief(record)


@app.get("/api/briefing")
def briefing_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    return briefing(threat_id, season, forecast_day)


def _municipal_features(collection: dict, municipality_slug: str | None) -> dict:
    if not municipality_slug:
        collection["features"] = []
        return collection
    own = municipality_slug
    collection["features"] = [
        feature
        for feature in collection.get("features") or []
        if feature["properties"]["slug"] == own or str(feature["properties"]["slug"]).startswith(f"{own}--")
    ]
    return collection


@app.get("/api/map")
def map_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    collection = map_features(threat_id, season, forecast_day)
    if user["role"] == "municipal":
        return _municipal_features(collection, user["municipality_slug"])
    return collection


@app.get("/api/analytics")
def analytics_route(
    threat_id: str = "all",
    season: str = "wet",
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    if threat_id != "all":
        threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    else:
        _selection("rice_blast", season, forecast_day)
        threat_id = None
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    return analytics(threat_id, season, forecast_day, user["role"], scope)


@app.post("/api/analytics/narrate")
def analytics_narrate_route(body: SelectionBody, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    threat_id = None if body.threat_id == "all" else body.threat_id
    if threat_id:
        threat_id, season, forecast_day = _selection(body.threat_id, body.season, body.forecast_day)
    else:
        _, season, forecast_day = _selection("rice_blast", body.season, body.forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    record = analytics(threat_id, season, forecast_day, user["role"], scope)
    return narrate_analytics(record)


@app.get("/api/rice")
def rice_route(
    threat_id: str = "rice_blast",
    season: str = "wet",
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    return rice(threat_id, season, forecast_day, user["role"], scope)


@app.post("/api/rice/narrate")
def rice_narrate_route(body: SelectionBody, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(body.threat_id, body.season, body.forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    record = rice(threat_id, season, forecast_day, user["role"], scope)
    return narrate_rice(record)


@app.get("/api/map/intel")
def map_intel_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    return map_intel(threat_id, season, forecast_day, user["role"], scope)


@app.get("/api/places/{slug}")
def place_route(
    slug: str,
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    own = user["municipality_slug"]
    if user["role"] == "municipal" and slug != own and not slug.startswith(f"{own}--"):
        raise HTTPException(status_code=403, detail="This account opens only its own municipality.")
    detail = place_detail(slug, threat_id, season, forecast_day)
    if not detail:
        raise HTTPException(status_code=404, detail="Place not found.")
    return detail


@app.get("/api/priority")
def priority_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    return priority(threat_id, season, forecast_day, scope)


@app.get("/api/algorithms")
def algorithms_route(
    threat_id: str,
    season: str,
    forecast_day: int = 0,
    authorization: str | None = Header(default=None),
):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(threat_id, season, forecast_day)
    payload = algorithms(threat_id, season, forecast_day)
    if user["role"] == "municipal":
        payload["priority"] = [row for row in payload["priority"] if row["slug"] == user["municipality_slug"]]
        payload["route"] = {
            "stops": payload["priority"] and [payload["priority"][0]["name"]] or [],
            "path": [],
            "distance_km": None,
            "note": "The provincial account sees the full inspection order. This account is limited to its municipality.",
        }
        own = payload["priority"][0]["name"] if payload["priority"] else None
        payload["clusters"] = [cluster for cluster in payload["clusters"] if own and own in cluster["names"]]
    return payload


@app.get("/api/lines")
def lines_route(kind: str, authorization: str | None = Header(default=None)):
    _user(authorization)
    if kind not in ("canal", "river", "road"):
        raise HTTPException(status_code=400, detail="Kind must be canal, river, or road.")
    return line_features(kind)


@app.post("/api/notes")
def add_note(body: NoteBody, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="The guest account cannot add field notes.")
    with connect() as conn:
        if "--" in body.place_slug:
            municipality_slug, barangay_slug = body.place_slug.split("--", 1)
            place = conn.execute(
                """
                SELECT b.id, m.slug FROM barangays b
                JOIN municipalities m ON m.id = b.municipality_id
                WHERE m.slug = %s AND b.slug = %s
                """,
                (municipality_slug, barangay_slug),
            ).fetchone()
            place_type = "barangay"
        else:
            place = conn.execute("SELECT id, slug FROM municipalities WHERE slug = %s", (body.place_slug,)).fetchone()
            place_type = "municipality"
        if not place:
            raise HTTPException(status_code=404, detail="Place not found.")
        if user["role"] == "municipal" and place["slug"] != user["municipality_slug"]:
            raise HTTPException(status_code=403, detail="Notes can be added only in your municipality.")
        row = conn.execute(
            """
            INSERT INTO field_notes (user_id, place_type, place_id, body)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (user["id"], place_type, place["id"], body.body.strip()),
        ).fetchone()
        conn.commit()
    return {"id": row["id"], "created_at": row["created_at"].isoformat()}


@app.post("/api/chat")
def chat_route(body: ChatBody, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    threat_id, season, forecast_day = _selection(body.threat_id, body.season, body.forecast_day)
    scope = user["municipality_slug"] if user["role"] == "municipal" else None
    return answer(body.message.strip(), threat_id, season, forecast_day, scope, user["role"])


@app.post("/api/recompute")
def recompute_route(authorization: str | None = Header(default=None)):
    user = _user(authorization)
    if user["role"] != "provincial":
        raise HTTPException(status_code=403, detail="Only the provincial account can recompute scores.")
    return recompute()


def _daily_refresh():
    from ingest.open_meteo import refresh

    return refresh()


def _microclimate_refresh():
    from ingest.microclimate import load

    return load()


async def _refresh_loop():
    await asyncio.sleep(30)
    while True:
        for label, job in (
            ("daily forecast", _daily_refresh),
            ("barangay microclimate", _microclimate_refresh),
            ("scores", recompute),
        ):
            try:
                await asyncio.to_thread(job)
            except Exception as exc:
                log.warning("%s skipped: %s", label, exc)
        await asyncio.sleep(6 * 60 * 60)
