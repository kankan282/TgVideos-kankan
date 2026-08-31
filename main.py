import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from tg_client import TGAuthManager
from speed_engine import SpeedEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = SpeedEngine()

# ─── Pydantic Models ───
class SendOTPReq(BaseModel):
    api_id: int
    api_hash: str
    phone: str

class VerifyOTPReq(BaseModel):
    otp: str

class Verify2FAReq(BaseModel):
    password: str

class ForwardReq(BaseModel):
    source: str
    target: str
    limit: int = 20

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto connect if session exists
    try:
        if await TGAuthManager.is_logged_in():
            logger.info("✅ Auto Logged in with saved session!")
    except Exception as e:
        logger.warning(f"Startup session check: {e}")
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health():
    return {"status": "ok"}

# ═══════════════════════════════════════════════════
# 🔐 AUTHENTICATION ENDPOINTS
# ═══════════════════════════════════════════════════

@app.get("/api/auth/status")
async def auth_status():
    logged = await TGAuthManager.is_logged_in()
    if logged:
        user = await TGAuthManager.get_me()
        return {
            "logged_in": True,
            "user": {
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "username": f"@{user.username}" if user.username else "No username",
                "phone": user.phone_number,
                "id": user.id
            }
        }
    return {"logged_in": False}

@app.post("/api/auth/send-otp")
async def send_otp(req: SendOTPReq):
    try:
        res = await TGAuthManager.send_otp(req.api_id, req.api_hash, req.phone)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/verify-otp")
async def verify_otp(req: VerifyOTPReq):
    try:
        res = await TGAuthManager.verify_otp(req.otp)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/verify-2fa")
async def verify_2fa(req: Verify2FAReq):
    try:
        res = await TGAuthManager.verify_2fa(req.password)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/logout")
async def logout():
    res = await TGAuthManager.logout()
    return {"success": True, "data": res}

# ═══════════════════════════════════════════════════
# ⚡ FORWARDING ENDPOINT
# ═══════════════════════════════════════════════════

@app.post("/api/forward/start")
async def start_forward(req: ForwardReq):
    if not await TGAuthManager.is_logged_in():
        raise HTTPException(401, "Pehle account login karo!")

    client = TGAuthManager.client
    source = req.source.strip()
    target = req.target.strip()

    if source.isdigit() or source.startswith("-"):
        source = int(source)
    if target.isdigit() or target.startswith("-"):
        target = int(target)

    messages = []
    async for msg in client.get_chat_history(source, limit=req.limit):
        messages.append(msg)

    if not messages:
        return {"success": False, "message": "Source channel me koi messages nahi mile"}

    # Run Parallel Forward
    result = await engine.bulk_forward(client, messages, target, ["all"])
    return {"success": True, "result": result}


# ═══════════════════════════════════════════════════
# 📱 VISUAL WEB DASHBOARD (HTML / JS / CSS)
# ═══════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ TG Forwarder Ultra Pro</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); }
    </style>
</head>
<body class="p-4 max-w-md mx-auto pb-20">

    <!-- Header -->
    <div class="flex items-center justify-between my-4">
        <div>
            <h1 class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">
                ⚡ TG Forwarder
            </h1>
            <p class="text-xs text-slate-400">Restricted Channel Auto-Cloner</p>
        </div>
        <div id="statusBadge" class="px-3 py-1 text-xs rounded-full bg-red-500/20 text-red-400 border border-red-500/30 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-red-400 animate-pulse"></span> Disconnected
        </div>
    </div>

    <!-- 1. ACCOUNT PANEL -->
    <div class="glass rounded-2xl p-5 mb-4 shadow-xl">
        <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-2">
            <i class="fa-solid fa-user-shield text-cyan-400"></i> Telegram Account
        </h2>

        <!-- State: Logged In -->
        <div id="loggedInView" class="hidden">
            <div class="bg-slate-800/60 rounded-xl p-3 border border-slate-700 mb-3 flex items-center justify-between">
                <div>
                    <p id="accName" class="font-bold text-white text-base"></p>
                    <p id="accUsername" class="text-xs text-cyan-400"></p>
                    <p id="accPhone" class="text-xs text-slate-400"></p>
                </div>
                <div class="bg-emerald-500/20 text-emerald-400 text-xs px-2.5 py-1 rounded-lg border border-emerald-500/30 font-medium">
                    Active
                </div>
            </div>
            <button onclick="logout()" class="w-full bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 font-semibold py-2.5 rounded-xl transition text-sm flex items-center justify-center gap-2">
                <i class="fa-solid fa-right-from-bracket"></i> Remove / Logout Account
            </button>
        </div>

        <!-- State: Step 1 (Credentials & Phone) -->
        <div id="step1View">
            <div class="space-y-3">
                <div>
                    <label class="text-xs text-slate-400 mb-1 block">API ID</label>
                    <input id="apiId" type="number" placeholder="e.g. 12345678" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-400 text-white">
                </div>
                <div>
                    <label class="text-xs text-slate-400 mb-1 block">API HASH</label>
                    <input id="apiHash" type="text" placeholder="e.g. f864ef50fdd7..." class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-400 text-white">
                </div>
                <div>
                    <label class="text-xs text-slate-400 mb-1 block">Phone Number (With Country Code)</label>
                    <input id="phone" type="text" placeholder="+58XXXXXXXXXX" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-400 text-white">
                </div>
                <button onclick="sendOTP()" id="sendOtpBtn" class="w-full bg-gradient-to-r from-cyan-500 to-blue-600 font-bold py-3 rounded-xl shadow-lg shadow-cyan-500/20 hover:opacity-90 transition text-sm flex items-center justify-center gap-2">
                    <span>Send Login OTP</span> <i class="fa-solid fa-paper-plane"></i>
                </button>
            </div>
        </div>

        <!-- State: Step 2 (OTP Input) -->
        <div id="step2View" class="hidden">
            <div class="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 text-xs mb-3">
                <i class="fa-solid fa-bell"></i> OTP tumhare <b>Telegram App</b> ke chat me aaya hoga!
            </div>
            <label class="text-xs text-slate-400 mb-1 block">Enter 5-Digit OTP Code</label>
            <input id="otpCode" type="text" placeholder="12345" class="w-full bg-slate-900/80 border border-cyan-500/50 rounded-xl px-3 py-3 text-center text-xl font-mono tracking-widest text-cyan-300 mb-3 focus:outline-none">
            
            <button onclick="verifyOTP()" id="verifyOtpBtn" class="w-full bg-emerald-500 hover:bg-emerald-600 font-bold py-3 rounded-xl shadow-lg shadow-emerald-500/20 transition text-sm mb-2">
                Verify & Login
            </button>
            <button onclick="resetAuthView()" class="w-full text-xs text-slate-400 hover:text-white py-1">Back</button>
        </div>

        <!-- State: Step 3 (2FA Password) -->
        <div id="step3View" class="hidden">
            <label class="text-xs text-slate-400 mb-1 block">Two-Step Verification Password</label>
            <input id="password2fa" type="password" placeholder="Enter 2FA Password" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm mb-3 focus:outline-none focus:border-cyan-400">
            <button onclick="verify2FA()" class="w-full bg-indigo-500 hover:bg-indigo-600 font-bold py-3 rounded-xl transition text-sm">
                Submit Password
            </button>
        </div>
    </div>

    <!-- 2. FAST FORWARD PANEL -->
    <div id="forwardPanel" class="glass rounded-2xl p-5 mb-4 shadow-xl opacity-50 pointer-events-none transition-all">
        <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-2">
            <i class="fa-solid fa-bolt text-yellow-400"></i> Fast Forward Task
        </h2>
        <div class="space-y-3">
            <div>
                <label class="text-xs text-slate-400 mb-1 block">Source Channel (Private/Restricted)</label>
                <input id="sourceChan" type="text" placeholder="@source_channel or -100xxxxxxx" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-400 text-white">
            </div>
            <div>
                <label class="text-xs text-slate-400 mb-1 block">Target Channel (Where you are admin)</label>
                <input id="targetChan" type="text" placeholder="@target_channel or -100xxxxxxx" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-400 text-white">
            </div>
            <div>
                <label class="text-xs text-slate-400 mb-1 block">Messages Count (Recent limit)</label>
                <input id="msgLimit" type="number" value="20" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-400 text-white">
            </div>

            <button onclick="startForward()" id="fwdBtn" class="w-full bg-gradient-to-r from-amber-500 to-orange-600 font-bold py-3.5 rounded-xl shadow-lg shadow-orange-500/20 hover:opacity-90 transition text-sm flex items-center justify-center gap-2">
                <i class="fa-solid fa-play"></i> ⚡ Start Ultra-Fast Clone
            </button>
        </div>
    </div>

    <!-- 3. LIVE LOGS -->
    <div class="glass rounded-2xl p-4 shadow-xl">
        <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <i class="fa-solid fa-terminal text-emerald-400"></i> Execution Output
        </h2>
        <div id="logs" class="bg-black/50 border border-slate-800 rounded-xl p-3 text-xs font-mono h-32 overflow-y-auto space-y-1 text-slate-300">
            <p class="text-slate-500">> Ready for commands...</p>
        </div>
    </div>

    <script>
        function log(msg, color="text-slate-300") {
            const el = document.getElementById("logs");
            el.innerHTML += `<p class="${color}">> ${msg}</p>`;
            el.scrollTop = el.scrollHeight;
        }

        async function checkStatus() {
            try {
                const r = await fetch('/api/auth/status');
                const d = await r.json();
                if(d.logged_in) {
                    document.getElementById("statusBadge").className = "px-3 py-1 text-xs rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5";
                    document.getElementById("statusBadge").innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400"></span> Connected';
                    
                    document.getElementById("accName").innerText = d.user.name || "User";
                    document.getElementById("accUsername").innerText = d.user.username;
                    document.getElementById("accPhone").innerText = "+" + d.user.phone;

                    document.getElementById("step1View").classList.add("hidden");
                    document.getElementById("step2View").classList.add("hidden");
                    document.getElementById("step3View").classList.add("hidden");
                    document.getElementById("loggedInView").classList.remove("hidden");
                    
                    // Enable Forwarding Panel
                    document.getElementById("forwardPanel").classList.remove("opacity-50", "pointer-events-none");
                } else {
                    resetAuthView();
                }
            } catch(e) {
                log("Status check failed", "text-red-400");
            }
        }

        function resetAuthView() {
            document.getElementById("statusBadge").className = "px-3 py-1 text-xs rounded-full bg-red-500/20 text-red-400 border border-red-500/30 flex items-center gap-1.5";
            document.getElementById("statusBadge").innerHTML = '<span class="w-2 h-2 rounded-full bg-red-400 animate-pulse"></span> Disconnected';
            document.getElementById("loggedInView").classList.add("hidden");
            document.getElementById("step2View").classList.add("hidden");
            document.getElementById("step3View").classList.add("hidden");
            document.getElementById("step1View").classList.remove("hidden");
            document.getElementById("forwardPanel").classList.add("opacity-50", "pointer-events-none");
        }

        async function sendOTP() {
            const api_id = parseInt(document.getElementById("apiId").value);
            const api_hash = document.getElementById("apiHash").value;
            const phone = document.getElementById("phone").value;

            if(!api_id || !api_hash || !phone) return alert("Saare fields bharo!");

            log("Sending OTP request to Telegram...", "text-yellow-400");
            document.getElementById("sendOtpBtn").disabled = true;

            try {
                const res = await fetch('/api/auth/send-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({api_id, api_hash, phone})
                });
                const data = await res.json();
                if(data.success) {
                    log("✅ OTP successfully sent! Check your Telegram App.", "text-emerald-400");
                    document.getElementById("step1View").classList.add("hidden");
                    document.getElementById("step2View").classList.remove("hidden");
                } else {
                    log("❌ Error: " + data.detail, "text-red-400");
                }
            } catch(e) {
                log("Error: " + e, "text-red-400");
            } finally {
                document.getElementById("sendOtpBtn").disabled = false;
            }
        }

        async function verifyOTP() {
            const otp = document.getElementById("otpCode").value;
            if(!otp) return alert("OTP daalo!");

            log("Verifying OTP...", "text-yellow-400");
            try {
                const res = await fetch('/api/auth/verify-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({otp})
                });
                const data = await res.json();
                if(data.success) {
                    if(data.data.status === "2fa_required") {
                        log("⚠️ 2FA Enabled! Password required.", "text-amber-400");
                        document.getElementById("step2View").classList.add("hidden");
                        document.getElementById("step3View").classList.remove("hidden");
                    } else {
                        log("🎉 Login Successful!", "text-emerald-400");
                        checkStatus();
                    }
                } else {
                    log("❌ " + data.detail, "text-red-400");
                }
            } catch(e) {
                log("Error: " + e, "text-red-400");
            }
        }

        async function verify2FA() {
            const password = document.getElementById("password2fa").value;
            if(!password) return alert("Password daalo!");

            try {
                const res = await fetch('/api/auth/verify-2fa', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({password})
                });
                const data = await res.json();
                if(data.success) {
                    log("🎉 2FA Verified & Login Successful!", "text-emerald-400");
                    checkStatus();
                } else {
                    log("❌ " + data.detail, "text-red-400");
                }
            } catch(e) {
                log("Error: " + e, "text-red-400");
            }
        }

        async function logout() {
            if(!confirm("Account remove karna chahte ho?")) return;
            log("Logging out...", "text-yellow-400");
            await fetch('/api/auth/logout', {method: 'POST'});
            log("Account successfully removed!", "text-cyan-400");
            checkStatus();
        }

        async function startForward() {
            const source = document.getElementById("sourceChan").value;
            const target = document.getElementById("targetChan").value;
            const limit = parseInt(document.getElementById("msgLimit").value);

            if(!source || !target) return alert("Source aur Target dono daalo!");

            log(`⚡ Cloning started: ${source} ➔ ${target}`, "text-cyan-400");
            document.getElementById("fwdBtn").disabled = true;

            try {
                const res = await fetch('/api/forward/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({source, target, limit})
                });
                const d = await res.json();
                if(d.success) {
                    log(`✅ Done in ${d.result.time}s! Success: ${d.result.success}, Failed: ${d.result.failed}`, "text-emerald-400");
                } else {
                    log("❌ " + (d.message || d.detail), "text-red-400");
                }
            } catch(e) {
                log("Forwarding error: " + e, "text-red-400");
            } finally {
                document.getElementById("fwdBtn").disabled = false;
            }
        }

        // On Load
        checkStatus();
    </script>
</body>
</html>
    """
