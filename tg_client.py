import os
import logging
import asyncio
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid,
    PhoneCodeExpired, PasswordHashInvalid,
    FloodWait, UserDeactivated, AuthKeyUnregistered
)

logger = logging.getLogger(__name__)
SESSION_FILE = "user_session"

class TGClient:
    client: Client = None
    phone_code_hash: str = None
    temp_phone: str = None
    _lock = asyncio.Lock()

    # ── Auth Flow ──

    @classmethod
    async def send_otp(cls, api_id: int, api_hash: str, phone: str):
        # Purana session hatao
        await cls._cleanup()

        cls.client = Client(
            name=SESSION_FILE, api_id=api_id,
            api_hash=api_hash, workdir="."
        )
        await cls.client.connect()

        try:
            sent = await cls.client.send_code(phone)
            cls.phone_code_hash = sent.phone_code_hash
            cls.temp_phone = phone
            return {"ok": True}
        except FloodWait as e:
            raise Exception(f"FloodWait! {e.value} sec baad try karo")
        except Exception as e:
            raise Exception(f"OTP bhejne me error: {e}")

    @classmethod
    async def verify_otp(cls, code: str):
        if not cls.client or not cls.phone_code_hash:
            raise Exception("Pehle OTP send karo!")
        try:
            user = await cls.client.sign_in(
                cls.temp_phone, cls.phone_code_hash, code.strip()
            )
            return {"ok": True, "status": "success", "name": user.first_name}
        except SessionPasswordNeeded:
            return {"ok": True, "status": "2fa"}
        except (PhoneCodeInvalid, PhoneCodeExpired):
            raise Exception("OTP galat ya expired hai!")

    @classmethod
    async def verify_2fa(cls, password: str):
        if not cls.client:
            raise Exception("Session nahi hai!")
        try:
            user = await cls.client.check_password(password)
            return {"ok": True, "name": user.first_name}
        except PasswordHashInvalid:
            raise Exception("2FA password galat hai!")

    # ── Session Management ──

    @classmethod
    async def ensure_connected(cls) -> Client:
        """Auto-reconnect agar disconnect ho gaya ho"""
        async with cls._lock:
            if cls.client is None:
                if not os.path.exists(f"{SESSION_FILE}.session"):
                    raise Exception("Koi session nahi hai! Pehle login karo.")
                # Session file se load karo — credentials .session me saved hote hain
                cls.client = Client(
                    name=SESSION_FILE,
                    api_id=0, api_hash="",  # Session file se auto-load
                    workdir="."
                )

            if not cls.client.is_connected:
                try:
                    await cls.client.connect()
                except Exception:
                    # Re-create client from session
                    cls.client = Client(
                        name=SESSION_FILE,
                        api_id=0, api_hash="",
                        workdir="."
                    )
                    await cls.client.connect()

            # Verify session is valid
            try:
                await cls.client.get_me()
            except (AuthKeyUnregistered, UserDeactivated):
                await cls._cleanup()
                raise Exception("Session expired! Dobara login karo.")

            return cls.client

    @classmethod
    async def is_logged_in(cls) -> bool:
        try:
            if not os.path.exists(f"{SESSION_FILE}.session"):
                return False
            client = await cls.ensure_connected()
            me = await client.get_me()
            return me is not None
        except Exception:
            return False

    @classmethod
    async def get_me(cls):
        try:
            client = await cls.ensure_connected()
            return await client.get_me()
        except Exception:
            return None

    @classmethod
    async def logout(cls):
        await cls._cleanup()
        return {"ok": True}

    @classmethod
    async def _cleanup(cls):
        try:
            if cls.client:
                if cls.client.is_connected:
                    try:
                        await cls.client.log_out()
                    except Exception:
                        await cls.client.disconnect()
                cls.client = None
        except Exception:
            pass
        for ext in [".session", ".session-journal"]:
            f = f"{SESSION_FILE}{ext}"
            if os.path.exists(f):
                os.remove(f)
