import os
import json
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
AUTH_STATE_FILE = "auth_state.json"

class TGClient:
    client: Client = None
    _lock = asyncio.Lock()

    @classmethod
    def _save_auth_state(cls, data: dict):
        with open(AUTH_STATE_FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def _load_auth_state(cls) -> dict:
        if os.path.exists(AUTH_STATE_FILE):
            try:
                with open(AUTH_STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @classmethod
    def _clear_auth_state(cls):
        if os.path.exists(AUTH_STATE_FILE):
            os.remove(AUTH_STATE_FILE)

    # ── Auth Flow ──

    @classmethod
    async def send_otp(cls, api_id: int, api_hash: str, phone: str):
        await cls._cleanup()

        cls.client = Client(
            name=SESSION_FILE,
            api_id=api_id,
            api_hash=api_hash,
            workdir="."
        )
        await cls.client.connect()

        try:
            sent = await cls.client.send_code(phone.strip())
            # Save hash to file so it never gets lost
            cls._save_auth_state({
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone.strip(),
                "phone_code_hash": sent.phone_code_hash
            })
            return {"ok": True, "message": "OTP sent successfully"}
        except FloodWait as e:
            raise Exception(f"FloodWait! {e.value} seconds wait karo")
        except Exception as e:
            raise Exception(f"OTP send error: {str(e)}")

    @classmethod
    async def verify_otp(cls, code: str):
        state = cls._load_auth_state()
        if not state.get("phone_code_hash"):
            raise Exception("Session state lost! Kripya dobara 'Send OTP' karein.")

        if cls.client is None or not cls.client.is_connected:
            cls.client = Client(
                name=SESSION_FILE,
                api_id=state["api_id"],
                api_hash=state["api_hash"],
                workdir="."
            )
            await cls.client.connect()

        try:
            user = await cls.client.sign_in(
                state["phone"],
                state["phone_code_hash"],
                code.strip()
            )
            cls._clear_auth_state()
            return {"ok": True, "status": "success", "name": user.first_name}
        except SessionPasswordNeeded:
            return {"ok": True, "status": "2fa"}
        except (PhoneCodeInvalid, PhoneCodeExpired):
            raise Exception("Galat ya Expired OTP!")
        except Exception as e:
            raise Exception(f"Verification error: {str(e)}")

    @classmethod
    async def verify_2fa(cls, password: str):
        if not cls.client:
            state = cls._load_auth_state()
            if not state.get("api_id"):
                raise Exception("Session nahi mila!")
            cls.client = Client(
                name=SESSION_FILE,
                api_id=state["api_id"],
                api_hash=state["api_hash"],
                workdir="."
            )
            await cls.client.connect()

        try:
            user = await cls.client.check_password(password.strip())
            cls._clear_auth_state()
            return {"ok": True, "name": user.first_name}
        except PasswordHashInvalid:
            raise Exception("2FA Password galat hai!")

    # ── Client Auto Reconnect ──

    @classmethod
    async def ensure_connected(cls) -> Client:
        async with cls._lock:
            if cls.client is None:
                if not os.path.exists(f"{SESSION_FILE}.session"):
                    raise Exception("No active login. Pehle Login karein.")
                cls.client = Client(
                    name=SESSION_FILE,
                    workdir="."
                )

            if not cls.client.is_connected:
                await cls.client.connect()

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
        cls._clear_auth_state()
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
                try:
                    os.remove(f)
                except Exception:
                    pass
