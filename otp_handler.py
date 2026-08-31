"""
╔══════════════════════════════════════════════════════════╗
║           🔐 OTP HANDLING - KAHA DALEGA?                ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  OPTION 1: Render Logs (RECOMMENDED)                     ║
║  ─────────────────────────────────────                   ║
║  1. Render dashboard → Your Service → Logs tab           ║
║  2. Waha dikhega: "🔐 Enter OTP: _"                     ║
║  3. Render ke "Shell" tab me jao                         ║
║  4. OTP type karo aur Enter maro                         ║
║                                                          ║
║  OPTION 2: API Endpoint (Smartest)                       ║
║  ─────────────────────────────────                       ║
║  1. Deploy hone ke baad /api/otp/submit pe POST karo     ║
║  2. OTP JSON body me bhejo                               ║
║  3. Automatically login ho jayega                        ║
║                                                          ║
║  OPTION 3: Local Terminal                                ║
║  ────────────────────────                                ║
║  1. python main.py run karo                              ║
║  2. Terminal me OTP maangega                             ║
║  3. Type karo → Done!                                    ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

class OTPManager:
    _otp_event = asyncio.Event()
    _otp_code = None
    _waiting = False

    @classmethod
    async def request_otp(cls, prompt: str = "🔐 Enter OTP") -> str:
        """OTP maangta hai - API ya Shell se"""
        cls._waiting = True
        cls._otp_event.clear()
        logger.info(f"\n{'='*50}")
        logger.info(f"  {prompt}")
        logger.info(f"  API se bhejo: POST /api/otp/submit")
        logger.info(f"  Ya Render Shell me type karo")
        logger.info(f"{'='*50}\n")

        # 5 minute wait karo OTP ka
        try:
            await asyncio.wait_for(cls._otp_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            cls._waiting = False
            raise TimeoutError("⏰ OTP timeout! 5 min me nahi aaya.")

        cls._waiting = False
        code = cls._otp_code
        cls._otp_code = None
        return code

    @classmethod
    def submit_otp(cls, code: str):
        """API endpoint se OTP receive karta hai"""
        if cls._waiting:
            cls._otp_code = code.strip()
            cls._otp_event.set()
            logger.info("✅ OTP Received!")
            return True
        return False

    @classmethod
    def is_waiting(cls) -> bool:
        return cls._waiting
