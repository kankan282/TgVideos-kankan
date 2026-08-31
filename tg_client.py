from pyrogram import Client
from config import Config
from otp_handler import OTPManager
import logging
import os

logger = logging.getLogger(__name__)

class TelegramClientManager:
    _client = None
    _lock = asyncio.Lock() if 'asyncio' in dir() else None

    @classmethod
    async def get_client(cls) -> Client:
        if cls._client and cls._client.is_connected:
            return cls._client

        import asyncio
        if not cls._lock:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._client and cls._client.is_connected:
                return cls._client

            cls._client = Client(
                name=Config.SESSION_NAME,
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                phone_number=Config.PHONE_NUMBER,
                phone_code=OTPManager.request_otp,  # 🔐 OTP handler
                workers=Config.MAX_WORKERS,
                sleep_threshold=10,
                max_concurrent_transmissions=Config.MAX_WORKERS,
            )

            try:
                await cls._client.start()
                me = await cls._client.get_me()
                logger.info(f"✅ Connected: {me.first_name} (@{me.username})")
            except Exception as e:
                logger.error(f"❌ Login failed: {e}")
                raise

        return cls._client

    @classmethod
    async def stop(cls):
        if cls._client and cls._client.is_connected:
            await cls._client.stop()

import asyncio
