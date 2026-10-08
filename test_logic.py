import asyncio
import sys
import database as db

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


async def run_tests():
    print("🚀 Initializing test database...")
    await db.init_db()

    # Create 4 test users
    users = [
        (101, "Иван", "", "ivan_santa"),
        (102, "Мария", "", "masha_snow"),
        (103, "Алексей", "", "alex_elf"),
        (104, "Елена", "", "elena_gifts")
    ]
    for uid, fn, ln, un in users:
        await db.upsert_user(uid, fn, ln, un)
    print("✅ Users created.")

    # 1. Иван creates room
    room = await db.create_room(creator_id=101, title="Новый Год 2026", budget="до 2000 ₽", description="Тест комнаты")
    room_id = room["id"]
    code = room["code"]
    print(f"✅ Room created: {room['title']} (Code: {code}, ID: {room_id})")

    # 2. Check initial condition: only 1 participant (Иван) -> Start must fail (< 3 participants)
    try:
        await db.start_lottery(room_id, admin_user_id=101)
        print("❌ FAILED: Lottery started with < 3 participants!")
    except ValueError as e:
        print(f"✅ PASSED (Check min 3 participants): {e}")

    # 3. Add Мария and Алексей (now 3 participants total: Иван, Мария, Алексей)
    await db.join_room(room_id, 102, wishlist="", anti_wishlist="")
    await db.join_room(room_id, 103, wishlist="", anti_wishlist="")

    # 4. Check wishlist condition: None of them wrote wishlist yet -> Start must fail!
    try:
        await db.start_lottery(room_id, admin_user_id=101)
        print("❌ FAILED: Lottery started with empty wishlists!")
    except ValueError as e:
        print(f"✅ PASSED (Check all wishlists filled): {e}")

    # 5. Non-admin tries to start (Мария uid=102) -> must fail!
    try:
        await db.start_lottery(room_id, admin_user_id=102)
        print("❌ FAILED: Non-admin was able to start lottery!")
    except ValueError as e:
        print(f"✅ PASSED (Check only admin can start): {e}")

    # 6. Fill wishes for Иван and Мария, but NOT Алексей -> Start must still fail!
    await db.update_participant_wishes(room_id, 101, wishlist="Тёплый вязаный свитер XL", anti_wishlist="Носки")
    await db.update_participant_wishes(room_id, 102, wishlist="Настольная игра Catan", anti_wishlist="Сладкое")

    try:
        await db.start_lottery(room_id, admin_user_id=101)
        print("❌ FAILED: Lottery started when 1 participant hadn't filled wishlist!")
    except ValueError as e:
        print(f"✅ PASSED (Check incomplete wishlists blocked): {e}")

    # 7. Алексей fills his wish! Also add Елена and fill her wish
    await db.update_participant_wishes(room_id, 103, wishlist="Беспроводные наушники", anti_wishlist="Книги")
    await db.join_room(room_id, 104, wishlist="Уютный плед", anti_wishlist="Кружки")

    # 8. Now admin (Иван) starts lottery! Must succeed!
    assignments = await db.start_lottery(room_id, admin_user_id=101)
    print(f"🎉 SUCCESS: Lottery completed! Assignments count: {len(assignments)}")

    # 9. Verify mathematical guarantees:
    # - No self-giving (A != B)
    # - No mutual gifting for N >= 3 (A -> B and B -> A)
    # - Every person gives to 1, receives from 1
    santas = [a["santa_id"] for a in assignments]
    receivers = [a["receiver_id"] for a in assignments]
    
    assert len(set(santas)) == 4, "Not all participants are santas!"
    assert len(set(receivers)) == 4, "Not all participants are receivers!"

    pair_map = {a["santa_id"]: a["receiver_id"] for a in assignments}
    for s, r in pair_map.items():
        assert s != r, f"Self-gifting detected: {s} -> {r}"
        assert pair_map[r] != s, f"Mutual gifting detected: {s} <-> {r}"
        print(f"🎅 {s} дарит подарок 🎁 {r}")

    print("✅ ALL ALGORITHM CONSTRAINTS AND MATHEMATICAL GUARANTEES PASSED!")

    # 10. Check that assignment query returns receiver details for participant
    ivan_target = await db.get_user_assignment(room_id, 101)
    print(f"Иван дарит: {ivan_target['first_name']} | Вишлист: {ivan_target['wishlist']}")
    assert ivan_target is not None

if __name__ == "__main__":
    asyncio.run(run_tests())
