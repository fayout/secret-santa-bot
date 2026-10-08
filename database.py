import aiosqlite
import random
import string
from datetime import datetime
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                budget TEXT,
                creator_id INTEGER NOT NULL,
                status TEXT DEFAULT 'LOBBY',
                created_at TEXT,
                FOREIGN KEY (creator_id) REFERENCES users (id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                wishlist TEXT,
                anti_wishlist TEXT,
                joined_at TEXT,
                UNIQUE (room_id, user_id),
                FOREIGN KEY (room_id) REFERENCES rooms (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                santa_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                assigned_at TEXT,
                UNIQUE (room_id, santa_id),
                FOREIGN KEY (room_id) REFERENCES rooms (id),
                FOREIGN KEY (santa_id) REFERENCES users (id),
                FOREIGN KEY (receiver_id) REFERENCES users (id)
            )
        """)
        await db.commit()

def generate_room_code(length=6) -> str:
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    return "SANTA-" + "".join(random.choices(chars, k=length))

async def upsert_user(user_id: int, first_name: str, last_name: str = "", username: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT INTO users (id, first_name, last_name, username, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                username=excluded.username
        """, (user_id, first_name or "Участник", last_name or "", username or "", now))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_room(creator_id: int, title: str, budget: str = "", description: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        code = generate_room_code()
        now = datetime.utcnow().isoformat()
        
        cursor = await db.execute("""
            INSERT INTO rooms (code, title, description, budget, creator_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'LOBBY', ?)
        """, (code, title, description, budget, creator_id, now))
        room_id = cursor.lastrowid

        # Creator automatically joins the room
        await db.execute("""
            INSERT INTO participants (room_id, user_id, wishlist, anti_wishlist, joined_at)
            VALUES (?, ?, '', '', ?)
        """, (room_id, creator_id, now))
        
        await db.commit()
        return await get_room_by_id(room_id)

async def get_room_by_id(room_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_room_by_code(code: str):
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rooms WHERE UPPER(code) = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def join_room(room_id: int, user_id: int, wishlist: str = "", anti_wishlist: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT INTO participants (room_id, user_id, wishlist, anti_wishlist, joined_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(room_id, user_id) DO UPDATE SET
                wishlist = CASE WHEN excluded.wishlist != '' THEN excluded.wishlist ELSE participants.wishlist END,
                anti_wishlist = CASE WHEN excluded.anti_wishlist != '' THEN excluded.anti_wishlist ELSE participants.anti_wishlist END
        """, (room_id, user_id, wishlist, anti_wishlist, now))
        await db.commit()

async def update_participant_wishes(room_id: int, user_id: int, wishlist: str, anti_wishlist: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE participants
            SET wishlist = ?, anti_wishlist = ?
            WHERE room_id = ? AND user_id = ?
        """, (wishlist, anti_wishlist, room_id, user_id))
        await db.commit()

async def remove_participant(room_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if room is lobby
        async with db.execute("SELECT status FROM rooms WHERE id = ?", (room_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != "LOBBY":
                raise ValueError("Нельзя удалять участников после запуска игры!")
                
        await db.execute("DELETE FROM participants WHERE room_id = ? AND user_id = ?", (room_id, user_id))
        await db.commit()

async def get_room_participants(room_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT p.user_id, p.wishlist, p.anti_wishlist, p.joined_at,
                   u.first_name, u.last_name, u.username
            FROM participants p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.room_id = ?
            ORDER BY p.joined_at ASC
        """
        async with db.execute(query, (room_id,)) as cursor:
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                row_dict = dict(r)
                has_wish = bool(row_dict.get("wishlist") and row_dict["wishlist"].strip())
                row_dict["is_ready"] = has_wish
                result.append(row_dict)
            return result

async def get_user_rooms(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT r.*,
                   (SELECT COUNT(*) FROM participants WHERE room_id = r.id) as participants_count,
                   (p.wishlist IS NOT NULL AND TRIM(p.wishlist) != '') as my_wish_ready
            FROM rooms r
            JOIN participants p ON r.id = p.room_id
            WHERE p.user_id = ?
            ORDER BY r.created_at DESC
        """
        async with db.execute(query, (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def start_lottery(room_id: int, admin_user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # 1. Check room and admin
        async with db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)) as cursor:
            room = await cursor.fetchone()
            if not room:
                raise ValueError("Комната не найдена")
            room = dict(room)

        if room["creator_id"] != admin_user_id:
            raise ValueError("Только администратор комнаты может запустить игру!")

        if room["status"] != "LOBBY":
            raise ValueError("Игра в этой комнате уже запущена!")

        # 2. Get participants
        participants = await get_room_participants(room_id)
        if len(participants) < 3:
            raise ValueError(f"Для запуска нужно минимум 3 участника! Сейчас участников: {len(participants)}")

        # 3. Check that everyone wrote a wishlist
        not_ready = [p for p in participants if not p["is_ready"]]
        if not_ready:
            names = ", ".join([p["first_name"] or str(p["user_id"]) for p in not_ready])
            raise ValueError(f"Не все участники написали свои желания! Ещё не заполнили: {names}")

        # 4. Derangement algorithm: Single Hamiltonian cycle to strictly eliminate self-gifting and mutual 2-cycles
        user_ids = [p["user_id"] for p in participants]
        random.shuffle(user_ids)
        
        n = len(user_ids)
        assignments = []
        now = datetime.utcnow().isoformat()
        
        for i in range(n):
            santa_id = user_ids[i]
            receiver_id = user_ids[(i + 1) % n]
            assignments.append((room_id, santa_id, receiver_id, now))

        await db.executemany("""
            INSERT INTO assignments (room_id, santa_id, receiver_id, assigned_at)
            VALUES (?, ?, ?, ?)
        """, assignments)

        await db.execute("UPDATE rooms SET status = 'STARTED' WHERE id = ?", (room_id,))
        await db.commit()

        return await get_all_assignments_with_details(room_id)

async def get_user_assignment(room_id: int, santa_user_id: int):
    """Returns who the user is gifting to, along with their wishlist and anti-wishlist."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT a.receiver_id, u.first_name, u.last_name, u.username,
                   p.wishlist, p.anti_wishlist
            FROM assignments a
            JOIN users u ON a.receiver_id = u.id
            JOIN participants p ON p.room_id = a.room_id AND p.user_id = a.receiver_id
            WHERE a.room_id = ? AND a.santa_id = ?
        """
        async with db.execute(query, (room_id, santa_user_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_all_assignments_with_details(room_id: int):
    """Used for sending notification messages to all participants."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT a.santa_id, a.receiver_id,
                   s.first_name as santa_name, s.username as santa_username,
                   r.first_name as receiver_name, r.last_name as receiver_last_name, r.username as receiver_username,
                   p.wishlist as receiver_wishlist, p.anti_wishlist as receiver_anti_wishlist,
                   rm.title as room_title, rm.budget as room_budget
            FROM assignments a
            JOIN users s ON a.santa_id = s.id
            JOIN users r ON a.receiver_id = r.id
            JOIN participants p ON p.room_id = a.room_id AND p.user_id = a.receiver_id
            JOIN rooms rm ON rm.id = a.room_id
            WHERE a.room_id = ?
        """
        async with db.execute(query, (room_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
