import os
import shutil
import logging
import asyncio
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PasswordHashInvalid
)

logger = logging.getLogger(__name__)

SESSION_NAME = "user_session"

class TGAuthManager:
    client: Client = None
    phone_code_hash: str = None
    temp_phone: str = None

    @classmethod
    def get_client(cls, api_id: int = None, api_hash: str = None) -> Client:
        if cls.client is None:
            # Agar session pehle se saved hai toh load karega
            cls.client = Client(
                name=SESSION_NAME,
                api_id=api_id or 12345,
                api_hash=api_hash or "dummy",
                workdir="."
            )
        return cls.client

    @classmethod
    async def is_logged_in(cls) -> bool:
        try:
            if not os.path.exists(f"{SESSION_NAME}.session"):
                return False
            client = cls.get_client()
            if not client.is_connected:
                await client.connect()
            me = await client.get_me()
            return me is not None
        except Exception:
            return False

    @classmethod
    async def get_me(cls):
        try:
            if await cls.is_logged_in():
                return await cls.client.get_me()
        except Exception:
            pass
        return None

    @classmethod
    async def send_otp(cls, api_id: int, api_hash: str, phone: str):
        """Step 1: Phone pe OTP bhejo"""
        if cls.client and cls.client.is_connected:
            await cls.client.disconnect()

        # Purana session clear karo naye login ke liye
        for ext in [".session", ".session-journal"]:
            if os.path.exists(f"{SESSION_NAME}{ext}"):
                os.remove(f"{SESSION_NAME}{ext}")

        cls.client = Client(
            name=SESSION_NAME,
            api_id=api_id,
            api_hash=api_hash,
            workdir="."
        )
        await cls.client.connect()
        sent_code = await cls.client.send_code(phone)
        cls.phone_code_hash = sent_code.phone_code_hash
        cls.temp_phone = phone
        return {"status": "otp_sent", "phone_code_hash": cls.phone_code_hash}

    @classmethod
    async def verify_otp(cls, otp_code: str):
        """Step 2: OTP verify karo"""
        if not cls.client or not cls.phone_code_hash or not cls.temp_phone:
            raise Exception("Pehle OTP send karo!")

        try:
            signed_in = await cls.client.sign_in(
                cls.temp_phone, cls.phone_code_hash, otp_code.strip()
            )
            return {"status": "success", "user": signed_in.first_name}
        except SessionPasswordNeeded:
            return {"status": "2fa_required", "message": "Two-Step Verification Password Chahiye!"}
        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            raise Exception(f"Galat ya expired OTP: {str(e)}")

    @classmethod
    async def verify_2fa(cls, password: str):
        """Step 3: Agar 2FA laga ho toh password verify karo"""
        if not cls.client:
            raise Exception("Client not connected!")
        try:
            signed_in = await cls.client.check_password(password)
            return {"status": "success", "user": signed_in.first_name}
        except PasswordHashInvalid:
            raise Exception("Galat 2FA Password!")

    @classmethod
    async def logout(cls):
        """Account delete / remove karo"""
        try:
            if cls.client:
                if cls.client.is_connected:
                    try:
                        await cls.client.log_out()
                    except Exception:
                        await cls.client.disconnect()
                cls.client = None
            
            for ext in [".session", ".session-journal"]:
                if os.path.exists(f"{SESSION_NAME}{ext}"):
                    os.remove(f"{SESSION_NAME}{ext}")
            return {"status": "logged_out"}
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return {"status": "error", "message": str(e)}
