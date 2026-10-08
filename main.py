import asyncio
import logging
import sys
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


from config import BOT_TOKEN, HOST, PORT
import database as db
import bot
from api import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("secret-santa")

@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup: init database
    logger.info("Initializing database...")
    await db.init_db()
    logger.info("Database initialized successfully.")

    # Startup Telegram bot polling if token is configured
    bot_task = None
    if bot.bot:
        logger.info("Starting Telegram Bot polling...")
        bot_task = asyncio.create_task(bot.dp.start_polling(bot.bot))
    else:
        logger.warning("BOT_TOKEN is not configured or placeholder! Bot polling disabled. WebApp is ready for browser testing.")

    yield

    # Shutdown
    if bot_task and not bot_task.done():
        logger.info("Stopping Telegram Bot polling...")
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

app.router.lifespan_context = lifespan

def main():
    logger.info(f"Starting Secret Santa server at http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

if __name__ == "__main__":
    main()
