import asyncio
import json
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from tg_client import TGClient
from forwarder import ForwardEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

engine = ForwardEngine()
log_queue = asyncio.Queue()

# ── Models ──
class OTPSend(BaseModel):
    api_id: int
    api_hash: str
    phone: str

class OTPVerify(BaseModel):
    otp: str

class TwoFA(BaseModel):
    password: str

class FwdReq(BaseModel):
    source: str
    target: str
    limit: int = 50
    types: List[str] = ["all"]

# ── App ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health():
    return {"status": "ok"}

# ══════════════════════════════════════
#  🔐 AUTH
# ══════════════════════════════════════

@app.get("/api/auth/status")
async def auth_status():
    if await TGClient.is_logged_in():
        me = await TGClient.get_me()
        return {
            "logged_in": True,
            "user": {
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": f"@{me.username}" if me.username else "—",
                "phone": me.phone_number or "—",
                "id": me.id
            }
        }
    return {"logged_in": False}

@app.post("/api/auth/send-otp")
async def send_otp(r: OTPSend):
    try:
        return await TGClient.send_otp(r.api_id, r.api_hash, r.phone)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/verify-otp")
async def verify_otp(r: OTPVerify):
    try:
        return await TGClient.verify_otp(r.otp)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/verify-2fa")
async def verify_2fa(r: TwoFA):
    try:
        return await TGClient.verify_2fa(r.password)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/logout")
async def logout():
    return await TGClient.logout()

# ══════════════════════════════════════
#  ⚡ FORWARDING
# ══════════════════════════════════════

@app.post("/api/forward/start")
async def start_forward(r: FwdReq):
    if not await TGClient.is_logged_in():
        raise HTTPException(401, "Pehle login karo!")

    # Clear old logs
    while not log_queue.empty():
        log_queue.get_nowait()

    async def progress_cb(msg, level):
        await log_queue.put({"msg": msg, "level": level, "ts": time.time()})

    # Run in background
    asyncio.create_task(
        engine.run(r.source, r.target, r.limit, r.types, progress_cb)
    )
    return {"ok": True, "message": "Forwarding started! Check logs."}

@app.post("/api/forward/stop")
async def stop_forward():
    engine.cancel()
    return {"ok": True, "message": "Stopping..."}

# ══════════════════════════════════════
#  📡 REAL-TIME LOGS (SSE)
# ══════════════════════════════════════

@app.get("/api/logs/stream")
async def log_stream():
    """Server-Sent Events — Real-time logs browser me dikhata hai"""
    async def event_generator():
        while True:
            try:
                data = await asyncio.wait_for(log_queue.get(), timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'msg': '💓 heartbeat', 'level': 'ping'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ══════════════════════════════════════
#  📱 WEB DASHBOARD
# ══════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>⚡ TG Forwarder Pro</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
*{box-sizing:border-box}
body{background:#0a0e1a;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0;padding:12px}
.glass{background:rgba(15,23,42,.85);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:16px;margin-bottom:12px}
input{width:100%;background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:10px 12px;color:#fff;font-size:14px;outline:none}
input:focus{border-color:#06b6d4}
.btn{width:100%;padding:12px;border-radius:12px;font-weight:700;font-size:14px;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;transition:.2s}
.btn:active{transform:scale(.97)}
.btn-cyan{background:linear-gradient(135deg,#06b6d4,#3b82f6);color:#fff}
.btn-green{background:linear-gradient(135deg,#10b981,#059669);color:#fff}
.btn-red{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3)}
.btn-orange{background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff}
.btn-gray{background:#1e293b;color:#94a3b8}
#logBox{background:#000;border:1px solid #1e293b;border-radius:10px;padding:10px;height:280px;overflow-y:auto;font-family:'Courier New',monospace;font-size:11px;line-height:1.6}
.log-success{color:#34d399}.log-error{color:#f87171}.log-warn{color:#fbbf24}
.log-skip{color:#64748b}.log-info{color:#94a3b8}.log-ping{color:#334155}
.badge{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;display:inline-flex;align-items:center;gap:5px}
.badge-on{background:rgba(16,185,129,.15);color:#34d399;border:1px solid rgba(16,185,129,.3)}
.badge-off{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3)}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot-on{background:#34d399}.dot-off{background:#f87171;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.hidden{display:none!important}
label{font-size:11px;color:#64748b;margin-bottom:4px;display:block}
</style>
</head>
<body>

<div style="max-width:420px;margin:0 auto">

<!-- HEADER -->
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
  <div>
    <h1 style="font-size:20px;font-weight:900;background:linear-gradient(90deg,#06b6d4,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0">⚡ TG Forwarder Pro</h1>
    <p style="font-size:10px;color:#475569;margin:2px 0 0">Restricted Channel Cloner</p>
  </div>
  <div id="badge" class="badge badge-off"><span class="dot dot-off"></span> Offline</div>
</div>

<!-- AUTH PANEL -->
<div class="glass" id="authPanel">
  <h3 style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin:0 0 12px">🔐 Account Setup</h3>

  <!-- Logged In View -->
  <div id="viewLoggedIn" class="hidden">
    <div style="background:#0f172a;border-radius:10px;padding:12px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center">
      <div>
        <div id="uName" style="font-weight:700;font-size:15px"></div>
        <div id="uUser" style="font-size:12px;color:#06b6d4"></div>
        <div id="uPhone" style="font-size:11px;color:#475569"></div>
      </div>
      <span class="badge badge-on"><span class="dot dot-on"></span> Active</span>
    </div>
    <button class="btn btn-red" onclick="doLogout()">🚪 Remove / Logout Account</button>
  </div>

  <!-- Step 1: Credentials -->
  <div id="viewStep1">
    <div style="display:flex;flex-direction:column;gap:8px">
      <div><label>API ID</label><input id="inApiId" type="number" placeholder="12345678"></div>
      <div><label>API HASH</label><input id="inApiHash" placeholder="f864ef50fdd7..."></div>
      <div><label>Phone (with country code)</label><input id="inPhone" placeholder="+58XXXXXXXXXX"></div>
      <button class="btn btn-cyan" onclick="doSendOTP()" id="btnSend">📨 Send OTP to Telegram</button>
    </div>
  </div>

  <!-- Step 2: OTP -->
  <div id="viewStep2" class="hidden">
    <div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.2);border-radius:10px;padding:10px;margin-bottom:10px;font-size:12px;color:#fbbf24">
      ⚠️ OTP tumhare <b>Telegram App</b> ke andar aaya hoga (SMS nahi!)
    </div>
    <label>5-Digit OTP Code</label>
    <input id="inOtp" placeholder="12345" style="text-align:center;font-size:22px;letter-spacing:8px;font-weight:700;color:#06b6d4">
    <button class="btn btn-green" onclick="doVerifyOTP()" style="margin-top:8px">✅ Verify & Login</button>
    <button class="btn btn-gray" onclick="showStep(1)" style="margin-top:6px">← Back</button>
  </div>

  <!-- Step 3: 2FA -->
  <div id="viewStep3" class="hidden">
    <label>2FA Password</label>
    <input id="in2fa" type="password" placeholder="Your 2FA password">
    <button class="btn btn-green" onclick="doVerify2FA()" style="margin-top:8px">🔓 Submit Password</button>
  </div>
</div>

<!-- FORWARD PANEL -->
<div class="glass" id="fwdPanel" style="opacity:.4;pointer-events:none">
  <h3 style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin:0 0 12px">⚡ Fast Forward</h3>
  <div style="display:flex;flex-direction:column;gap:8px">
    <div>
      <label>Source Channel / Message Link</label>
      <input id="inSrc" placeholder="@channel or t.me/channel/14">
    </div>
    <div>
      <label>Target Channel (You must be admin)</label>
      <input id="inTgt" placeholder="@my_channel or -100xxxx">
    </div>
    <div>
      <label>Message Limit (kitne msg forward karne hain)</label>
      <input id="inLimit" type="number" value="30" min="1" max="500">
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-orange" onclick="doForward()" id="btnFwd" style="flex:1">▶ Start Clone</button>
      <button class="btn btn-red" onclick="doStop()" style="flex:.4">⏹</button>
    </div>
  </div>
</div>

<!-- LIVE LOGS -->
<div class="glass">
  <h3 style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px">📡 Live Logs</h3>
  <div id="logBox"><span class="log-info">> Waiting...</span></div>
</div>

</div>

<script>
const $ = id => document.getElementById(id);

function showStep(n) {
  $('viewStep1').classList.toggle('hidden', n!==1);
  $('viewStep2').classList.toggle('hidden', n!==2);
  $('viewStep3').classList.toggle('hidden', n!==3);
  $('viewLoggedIn').classList.toggle('hidden', n!==0);
}

function addLog(msg, level='info') {
  const box = $('logBox');
  const t = new Date().toLocaleTimeString();
  box.innerHTML += `<div class="log-${level}">[${t}] ${msg}</div>`;
  box.scrollTop = box.scrollHeight;
}

// ── SSE Real-time Logs ──
function connectLogs() {
  const es = new EventSource('/api/logs/stream');
  es.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      if (d.level !== 'ping') addLog(d.msg, d.level);
    } catch {}
  };
  es.onerror = () => setTimeout(connectLogs, 3000);
}
connectLogs();

// ── Auth Status ──
async function checkAuth() {
  try {
    const r = await fetch('/api/auth/status');
    const d = await r.json();
    if (d.logged_in) {
      $('uName').textContent = d.user.name;
      $('uUser').textContent = d.user.username;
      $('uPhone').textContent = '+' + d.user.phone;
      showStep(0);
      $('badge').className = 'badge badge-on';
      $('badge').innerHTML = '<span class="dot dot-on"></span> Online';
      $('fwdPanel').style.opacity = '1';
      $('fwdPanel').style.pointerEvents = 'auto';
    } else {
      showStep(1);
      $('badge').className = 'badge badge-off';
      $('badge').innerHTML = '<span class="dot dot-off"></span> Offline';
      $('fwdPanel').style.opacity = '.4';
      $('fwdPanel').style.pointerEvents = 'none';
    }
  } catch {}
}

async function doSendOTP() {
  const api_id = parseInt($('inApiId').value);
  const api_hash = $('inApiHash').value;
  const phone = $('inPhone').value;
  if (!api_id || !api_hash || !phone) return alert('Sab fields bharo!');
  $('btnSend').textContent = '⏳ Sending...';
  try {
    const r = await fetch('/api/auth/send-otp', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({api_id, api_hash, phone})
    });
    const d = await r.json();
    if (d.ok || r.ok) {
      addLog('✅ OTP sent! Check Telegram App.', 'success');
      showStep(2);
    } else {
      addLog('❌ ' + (d.detail||'Error'), 'error');
    }
  } catch(e) { addLog('❌ '+e, 'error'); }
  $('btnSend').textContent = '📨 Send OTP to Telegram';
}

async function doVerifyOTP() {
  const otp = $('inOtp').value;
  if (!otp) return;
  try {
    const r = await fetch('/api/auth/verify-otp', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({otp})
    });
    const d = await r.json();
    if (d.status === '2fa') {
      addLog('⚠️ 2FA Password chahiye!', 'warn');
      showStep(3);
    } else if (d.status === 'success' || r.ok) {
      addLog('🎉 Login Successful!', 'success');
      checkAuth();
    } else {
      addLog('❌ '+(d.detail||'Error'), 'error');
    }
  } catch(e) { addLog('❌ '+e, 'error'); }
}

async function doVerify2FA() {
  const pw = $('in2fa').value;
  if (!pw) return;
  try {
    const r = await fetch('/api/auth/verify-2fa', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({password: pw})
    });
    const d = await r.json();
    if (r.ok) { addLog('🎉 2FA Done!', 'success'); checkAuth(); }
    else addLog('❌ '+(d.detail||'Error'), 'error');
  } catch(e) { addLog('❌ '+e, 'error'); }
}

async function doLogout() {
  if (!confirm('Account hata do?')) return;
  await fetch('/api/auth/logout', {method:'POST'});
  addLog('🚪 Logged out!', 'warn');
  checkAuth();
}

async function doForward() {
  const source = $('inSrc').value;
  const target = $('inTgt').value;
  const limit = parseInt($('inLimit').value) || 30;
  if (!source || !target) return alert('Source aur Target dono daalo!');
  $('btnFwd').textContent = '⏳ Running...';
  $('btnFwd').disabled = true;
  $('logBox').innerHTML = '';
  addLog('🚀 Forwarding started...', 'info');
  try {
    await fetch('/api/forward/start', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source, target, limit, types:['all']})
    });
  } catch(e) { addLog('❌ '+e, 'error'); }
  setTimeout(() => {
    $('btnFwd').textContent = '▶ Start Clone';
    $('btnFwd').disabled = false;
  }, 5000);
}

async function doStop() {
  await fetch('/api/forward/stop', {method:'POST'});
  addLog('⏹ Stopped!', 'warn');
}

checkAuth();
</script>
</body>
</html>"""
