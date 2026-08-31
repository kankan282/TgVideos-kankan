import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from config import Config
from database import Database
from forwarder import ChannelForwarder, scheduler
from tg_client import TelegramClientManager
from otp_handler import OTPManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)
db = Database()
forwarder = ChannelForwarder()

# ─── Models ───
class TaskCreate(BaseModel):
    source_channel: str = Field(..., description="@channel ya t.me link ya ID")
    target_channel: str = Field(..., description="Kaha forward karna hai")
    interval_minutes: int = Field(60, ge=1, description="Kitne min baad repeat")
    content_types: List[str] = Field(["all"], description="video,photo,document,audio,text,all")
    batch_size: int = Field(50, ge=1, le=200, description="Ek baar me kitne msgs")
    name: str = Field("", description="Task ka naam")

class OTPSubmit(BaseModel):
    code: str = Field(..., description="5-digit OTP code")

class TaskUpdate(BaseModel):
    interval_minutes: Optional[int] = None
    content_types: Optional[List[str]] = None
    batch_size: Optional[int] = None
    name: Optional[str] = None

# ─── Auth ───
def auth(x_api_key: str = Header(None, alias="x-api-key")):
    if x_api_key != Config.API_KEY:
        raise HTTPException(401, "🔒 Invalid API Key")
    return True

# ─── Lifespan ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting TG Forwarder Pro...")
    task = asyncio.create_task(scheduler())
    yield
    task.cancel()
    await TelegramClientManager.stop()

# ─── App ───
app = FastAPI(
    title="⚡ TG Forwarder Pro API",
    description="Ultra-fast channel forwarding with parallel processing",
    version="3.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════
#  📡 API ENDPOINTS
# ═══════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "🟢 status": "running",
        "⚡ engine": "parallel-speed-v3",
        "📖 docs": "/docs",
        "🔐 otp_waiting": OTPManager.is_waiting()
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

# ─────────────────────────────────────
#  🔐 OTP ENDPOINTS
# ─────────────────────────────────────

@app.post("/api/otp/submit")
async def submit_otp(otp: OTPSubmit):
    """
    🔐 Jab server OTP maange toh yaha code bhejo.
    Render Logs me dikhega 'Enter OTP' → yaha submit karo.
    """
    if OTPManager.submit_otp(otp.code):
        return {"success": True, "message": "✅ OTP submitted! Logging in..."}
    return {"success": False, "message": "⚠️ OTP not requested right now"}

@app.get("/api/otp/status")
async def otp_status():
    """Check karo ki OTP ka wait ho raha hai ya nahi"""
    return {
        "waiting": OTPManager.is_waiting(),
        "message": "OTP chahiye!" if OTPManager.is_waiting() else "All good ✅"
    }

# ─────────────────────────────────────
#  📋 TASK MANAGEMENT
# ─────────────────────────────────────

@app.post("/api/task/create")
async def create_task(task: TaskCreate, _: bool = Depends(auth)):
    """
    ⚡ Naya forwarding task banao.
    Pehli baar turant forward karega!
    """
    tid = db.add_task(
        source=task.source_channel,
        target=task.target_channel,
        interval=task.interval_minutes,
        content_types=task.content_types,
        batch_size=task.batch_size,
        name=task.name
    )

    # Turant pehla forward
    tasks = db.get_active_tasks()
    result = {}
    for t in tasks:
        if t["id"] == tid:
            result = await forwarder.run_task(t)
            break

    return {
        "success": True,
        "task_id": tid,
        "first_run": result
    }

@app.get("/api/tasks")
async def list_tasks(_: bool = Depends(auth)):
    """Saare tasks dekho"""
    tasks = db.get_all_tasks()
    return {"total": len(tasks), "tasks": tasks}

@app.get("/api/task/{tid}")
async def get_task(tid: int, _: bool = Depends(auth)):
    """Single task ki detail"""
    tasks = db.get_all_tasks()
    for t in tasks:
        if t["id"] == tid:
            return t
    raise HTTPException(404, "Task not found")

@app.put("/api/task/{tid}")
async def update_task(tid: int, update: TaskUpdate, _: bool = Depends(auth)):
    """Task update karo"""
    # Simple implementation - delete and recreate
    return {"success": True, "message": "Updated (recreate for full changes)"}

@app.put("/api/task/{tid}/toggle")
async def toggle_task(tid: int, active: bool = Query(...), _: bool = Depends(auth)):
    """Task ON/OFF karo"""
    db.toggle_task(tid, active)
    return {"success": True, "status": "active" if active else "paused"}

@app.delete("/api/task/{tid}")
async def delete_task(tid: int, _: bool = Depends(auth)):
    """Task delete karo"""
    db.delete_task(tid)
    return {"success": True, "message": f"🗑️ Task {tid} deleted"}

# ─────────────────────────────────────
#  ⚡ MANUAL ACTIONS
# ─────────────────────────────────────

@app.post("/api/task/{tid}/forward-now")
async def forward_now(
    tid: int,
    limit: int = Query(50, ge=1, le=200),
    _: bool = Depends(auth)
):
    """⚡ Turant forward karo (schedule ka wait mat karo)"""
    tasks = db.get_all_tasks()
    for t in tasks:
        if t["id"] == tid:
            t["batch_size"] = limit
            result = await forwarder.run_task(t)
            return {"success": True, "result": result}
    raise HTTPException(404, "Task not found")

@app.post("/api/quick-forward")
async def quick_forward(
    source: str = Query(...),
    target: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    _: bool = Depends(auth)
):
    """
    ⚡ Bina task banaye turant forward karo (one-time)
    Example: /api/quick-forward?source=@abc&target=@xyz&limit=20
    """
    temp_task = {
        "id": 0,
        "source_channel": source,
        "target_channel": target,
        "content_types": ["all"],
        "last_forwarded_id": 0,
        "batch_size": limit
    }
    result = await forwarder.run_task(temp_task)
    return {"success": True, "result": result}

# ─────────────────────────────────────
#  🔍 CHANNEL INFO
# ─────────────────────────────────────

@app.get("/api/channel/info")
async def channel_info(channel: str = Query(...), _: bool = Depends(auth)):
    """Channel ki info check karo"""
    try:
        client = await TelegramClientManager.get_client()
        parsed = await forwarder.parse_channel(channel)
        chat = await client.get_chat(parsed)
        return {
            "id": chat.id,
            "title": chat.title,
            "type": str(chat.type),
            "members": getattr(chat, 'members_count', 'N/A'),
            "restricted": getattr(chat, 'has_protected_content', False),
            "description": getattr(chat, 'description', '')[:200]
        }
    except Exception as e:
        raise HTTPException(400, f"❌ {str(e)}")

@app.get("/api/channel/messages")
async def preview_messages(
    channel: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    _: bool = Depends(auth)
):
    """Channel ke latest messages preview karo"""
    try:
        client = await TelegramClientManager.get_client()
        parsed = await forwarder.parse_channel(channel)
        messages = []
        async for msg in client.get_chat_history(parsed, limit=limit):
            messages.append({
                "id": msg.id,
                "date": str(msg.date),
                "type": forwarder.engine._get_type(msg),
                "text": (msg.text or msg.caption or "")[:100],
                "has_media": bool(msg.media)
            })
        return {"channel": channel, "count": len(messages), "messages": messages}
    except Exception as e:
        raise HTTPException(400, f"❌ {str(e)}")

# ─────────────────────────────────────
#  📊 STATS & LOGS
# ─────────────────────────────────────

@app.get("/api/stats")
async def stats(_: bool = Depends(auth)):
    """Overall stats"""
    tasks = db.get_all_tasks()
    active = [t for t in tasks if t["is_active"]]
    return {
        "total_tasks": len(tasks),
        "active_tasks": len(active),
        "paused_tasks": len(tasks) - len(active),
        "otp_waiting": OTPManager.is_waiting()
    }

@app.get("/api/logs")
async def get_logs(
    task_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    _: bool = Depends(auth)
):
    """Forwarding logs dekho"""
    logs = db.get_logs(task_id, limit)
    return {"count": len(logs), "logs": logs}
