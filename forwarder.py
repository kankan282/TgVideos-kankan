import asyncio
import time
import logging
from tg_client import TelegramClientManager
from speed_engine import SpeedEngine
from database import Database

logger = logging.getLogger(__name__)
db = Database()

class ChannelForwarder:

    def __init__(self):
        self.engine = SpeedEngine()

    async def parse_channel(self, input_str: str):
        """Channel link/username/ID parse karo"""
        s = input_str.strip()
        if s.startswith("@"):
            return s
        if "t.me/" in s:
            part = s.split("t.me/")[-1].split("/")[0].split("?")[0]
            if part.startswith("+"):
                return s  # Private invite link
            return f"@{part}"
        if s.lstrip("-").isdigit():
            return int(s)
        return s

    async def run_task(self, task: dict) -> dict:
        """Ek task execute karo with speed engine"""
        start = time.time()
        try:
            client = await TelegramClientManager.get_client()
            source = await self.parse_channel(task["source_channel"])
            target = await self.parse_channel(task["target_channel"])
            content_types = task["content_types"]
            last_id = task["last_forwarded_id"]
            limit = task.get("batch_size", 50)

            logger.info(f"🔄 Task {task['id']}: {source} → {target}")

            # Fetch messages
            messages = []
            async for msg in client.get_chat_history(source, limit=limit):
                if msg.id <= last_id:
                    break
                messages.append(msg)

            if not messages:
                return {"forwarded": 0, "time": 0, "status": "no_new"}

            # ⚡ Speed Engine se bulk forward
            result = await self.engine.bulk_forward(
                client, messages, target, content_types
            )

            # Update last ID
            if result["success"] > 0:
                latest_id = max(m.id for m in messages)
                db.update_last_id(task["id"], latest_id)

            result["total_time"] = round(time.time() - start, 2)
            result["status"] = "completed"
            return result

        except Exception as e:
            logger.error(f"❌ Task {task['id']}: {e}")
            return {"forwarded": 0, "error": str(e), "status": "error"}


# ─── Background Scheduler ───
async def scheduler():
    forwarder = ChannelForwarder()
    last_run = {}
    logger.info("🕐 Scheduler running...")

    while True:
        try:
            tasks = db.get_active_tasks()
            now = time.time()

            for task in tasks:
                tid = task["id"]
                interval = task["interval_minutes"] * 60
                if now - last_run.get(tid, 0) >= interval:
                    result = await forwarder.run_task(task)
                    last_run[tid] = now
                    logger.info(f"📊 Task {tid}: {result}")

        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        await asyncio.sleep(15)  # Har 15 sec check
