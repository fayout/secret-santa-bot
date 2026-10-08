import json
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

from config import BOT_USERNAME, WEBAPP_URL, BASE_DIR
import database as db
import bot

logger = logging.getLogger(__name__)

app = FastAPI(title="Secret Santa Mini App API")

# Mount static files
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Request Models
class UserSyncRequest(BaseModel):
    user_id: int
    first_name: str
    last_name: Optional[str] = ""
    username: Optional[str] = ""

class CreateRoomRequest(BaseModel):
    user_id: int
    title: str
    budget: Optional[str] = ""
    description: Optional[str] = ""

class JoinRoomRequest(BaseModel):
    user_id: int
    wishlist: Optional[str] = ""
    anti_wishlist: Optional[str] = ""

class UpdateWishlistRequest(BaseModel):
    user_id: int
    wishlist: str
    anti_wishlist: Optional[str] = ""

class StartLotteryRequest(BaseModel):
    user_id: int

@app.get("/")
async def serve_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Secret Santa API is running. Place index.html in static/"}

@app.get("/api/config")
async def get_config():
    return {
        "bot_username": BOT_USERNAME,
        "webapp_url": WEBAPP_URL
    }

@app.post("/api/auth/sync")
async def sync_user(req: UserSyncRequest):
    await db.upsert_user(
        user_id=req.user_id,
        first_name=req.first_name,
        last_name=req.last_name or "",
        username=req.username or ""
    )
    user = await db.get_user(req.user_id)
    return {"status": "ok", "user": user}

@app.get("/api/rooms/my")
async def get_my_rooms(user_id: int):
    rooms = await db.get_user_rooms(user_id)
    return {"rooms": rooms}

@app.post("/api/rooms")
async def create_room_endpoint(req: CreateRoomRequest):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Название комнаты обязательно!")
    
    # Ensure creator is in users DB
    creator = await db.get_user(req.user_id)
    if not creator:
        await db.upsert_user(req.user_id, f"User {req.user_id}")

    room = await db.create_room(
        creator_id=req.user_id,
        title=req.title.strip(),
        budget=req.budget.strip() if req.budget else "",
        description=req.description.strip() if req.description else ""
    )
    return {"room": room}

@app.get("/api/rooms/by-code/{code}")
async def get_room_details(code: str, user_id: int):
    room = await db.get_room_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    participants = await db.get_room_participants(room["id"])
    
    # Check if the requesting user is in the room
    my_participant_info = next((p for p in participants if p["user_id"] == user_id), None)
    is_joined = my_participant_info is not None
    is_admin = room["creator_id"] == user_id

    # If game has started, get my assignment (target)
    my_target = None
    if room["status"] == "STARTED" and is_joined:
        my_target = await db.get_user_assignment(room["id"], user_id)

    # Privacy mask: other participants' actual wishes are secret during lobby,
    # but we show who has filled it (`is_ready: True/False`).
    # Only for the requesting user do we include their own wishlist.
    sanitized_participants = []
    for p in participants:
        is_me = p["user_id"] == user_id
        sanitized_participants.append({
            "user_id": p["user_id"],
            "first_name": p["first_name"] or "Участник",
            "last_name": p["last_name"] or "",
            "username": p["username"] or "",
            "is_ready": p["is_ready"],
            "is_creator": p["user_id"] == room["creator_id"],
            "wishlist": p["wishlist"] if is_me else None,
            "anti_wishlist": p["anti_wishlist"] if is_me else None,
        })

    ready_count = sum(1 for p in participants if p["is_ready"])
    all_ready = len(participants) >= 3 and ready_count == len(participants)

    return {
        "room": room,
        "is_admin": is_admin,
        "is_joined": is_joined,
        "my_info": my_participant_info,
        "participants": sanitized_participants,
        "stats": {
            "total_participants": len(participants),
            "ready_count": ready_count,
            "min_required": 3,
            "can_start": is_admin and room["status"] == "LOBBY" and all_ready
        },
        "target": my_target
    }

@app.post("/api/rooms/{code}/join")
async def join_room_endpoint(code: str, req: JoinRoomRequest):
    room = await db.get_room_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    if room["status"] != "LOBBY":
        raise HTTPException(status_code=400, detail="Игра уже началась! Вступить нельзя.")

    await db.join_room(
        room_id=room["id"],
        user_id=req.user_id,
        wishlist=req.wishlist or "",
        anti_wishlist=req.anti_wishlist or ""
    )
    return {"status": "ok"}

@app.post("/api/rooms/{code}/wishlist")
async def update_wishlist_endpoint(code: str, req: UpdateWishlistRequest):
    room = await db.get_room_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    if not req.wishlist.strip():
        raise HTTPException(status_code=400, detail="Желание не может быть пустым!")

    await db.update_participant_wishes(
        room_id=room["id"],
        user_id=req.user_id,
        wishlist=req.wishlist.strip(),
        anti_wishlist=req.anti_wishlist.strip() if req.anti_wishlist else ""
    )
    return {"status": "ok"}

@app.post("/api/rooms/{code}/start")
async def start_lottery_endpoint(code: str, req: StartLotteryRequest):
    room = await db.get_room_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    try:
        assignments = await db.start_lottery(room["id"], req.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Send telegram notifications in background
    try:
        await bot.notify_lottery_started(assignments)
    except Exception as e:
        logger.error(f"Failed to dispatch Telegram notifications: {e}")

    # Return my assigned target
    my_target = await db.get_user_assignment(room["id"], req.user_id)
    return {
        "status": "started",
        "target": my_target
    }

@app.delete("/api/rooms/{code}/participants/{target_user_id}")
async def kick_participant_endpoint(code: str, target_user_id: int, user_id: int):
    room = await db.get_room_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    if room["creator_id"] != user_id:
        raise HTTPException(status_code=403, detail="Только создатель комнаты может исключать участников!")

    if target_user_id == room["creator_id"]:
        raise HTTPException(status_code=400, detail="Создатель не может исключить сам себя из комнаты!")

    try:
        await db.remove_participant(room["id"], target_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok"}
