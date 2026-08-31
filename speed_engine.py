"""
⚡ SPEED ENGINE - Parallel Download + Upload
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Yeh engine multiple files ko EK SAATH process karta hai.

Normal:  File1 → File2 → File3 → File4 → File5  (Sequential)
Speed:   File1 ┐
         File2 ├→ ALL AT ONCE (Parallel)
         File3 ┘

200-300MB video:
- Normal: 2-5 min
- Speed Engine: 30-90 sec (server speed pe depend)
"""

import asyncio
import os
import time
import tempfile
import logging
from typing import List, Optional
from pyrogram.types import Message
from pyrogram import Client
from config import Config

logger = logging.getLogger(__name__)

class SpeedEngine:

    def __init__(self, max_workers: int = None):
        self.max_workers = max_workers or Config.MAX_WORKERS
        self.semaphore = asyncio.Semaphore(self.max_workers)
        self.temp_dir = tempfile.mkdtemp(prefix="tg_fwd_")

    async def bulk_forward(
        self,
        client: Client,
        messages: List[Message],
        target: str,
        content_types: List[str]
    ) -> dict:
        """
        ⚡ Multiple messages ko parallel forward karta hai
        Returns: {"success": int, "failed": int, "skipped": int, "time": float}
        """
        start_time = time.time()
        results = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

        # Filter messages by content type
        filtered = []
        for msg in messages:
            msg_type = self._get_type(msg)
            if "all" in content_types or msg_type in content_types:
                filtered.append(msg)
            else:
                results["skipped"] += 1

        if not filtered:
            results["time"] = time.time() - start_time
            return results

        logger.info(f"⚡ Processing {len(filtered)} messages with {self.max_workers} workers")

        # Parallel processing
        tasks = [
            self._process_single(client, msg, target)
            for msg in filtered
        ]

        done = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(done):
            if isinstance(result, Exception):
                results["failed"] += 1
                results["errors"].append(f"Msg {filtered[i].id}: {str(result)}")
            elif result:
                results["success"] += 1
            else:
                results["failed"] += 1

        results["time"] = round(time.time() - start_time, 2)
        logger.info(
            f"✅ Done in {results['time']}s | "
            f"OK: {results['success']} | "
            f"Fail: {results['failed']} | "
            f"Skip: {results['skipped']}"
        )
        return results

    async def _process_single(
        self, client: Client, message: Message, target: str
    ) -> bool:
        """Single message ko fast process karo"""
        async with self.semaphore:
            try:
                # Pehle direct forward try karo (fastest)
                try:
                    await message.forward(target)
                    return True
                except Exception:
                    pass  # Restricted hai, copy karna padega

                # Restricted channel → Download + Upload
                return await self._copy_restricted(client, message, target)

            except Exception as e:
                logger.error(f"❌ Msg {message.id}: {e}")
                return False

    async def _copy_restricted(
        self, client: Client, message: Message, target: str
    ) -> bool:
        """Restricted content ko download + re-upload karo"""

        # Text only
        if message.text and not any([
            message.video, message.photo, message.document,
            message.audio, message.animation, message.sticker
        ]):
            await client.send_message(target, message.text)
            return True

        # Media content - Download with progress
        file_path = None
        try:
            # Download
            file_path = await message.download(
                file_name=self.temp_dir,
                in_memory=False
            )

            if not file_path or not os.path.exists(file_path):
                return False

            caption = message.caption or ""

            # Upload based on type
            if message.video:
                await client.send_video(
                    target, file_path,
                    caption=caption,
                    width=message.video.width,
                    height=message.video.height,
                    duration=message.video.duration,
                    supports_streaming=True,  # ⚡ Streaming support
                    progress=self._upload_progress
                )
            elif message.photo:
                await client.send_photo(target, file_path, caption=caption)

            elif message.document:
                await client.send_document(
                    target, file_path, caption=caption,
                    progress=self._upload_progress
                )

            elif message.audio:
                await client.send_audio(
                    target, file_path, caption=caption,
                    duration=message.audio.duration,
                    title=message.audio.title,
                    performer=message.audio.performer
                )

            elif message.animation:
                await client.send_animation(
                    target, file_path, caption=caption
                )

            elif message.sticker:
                await client.send_sticker(target, file_path)

            elif message.voice:
                await client.send_voice(target, file_path)

            else:
                if caption:
                    await client.send_message(target, caption)

            return True

        finally:
            # Cleanup temp file
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

    async def _upload_progress(self, current, total):
        """Upload progress logger (large files ke liye)"""
        if total > 50 * 1024 * 1024:  # 50MB+ files
            pct = (current / total) * 100
            if int(pct) % 25 == 0:
                mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                logger.info(f"📤 Upload: {mb:.1f}/{total_mb:.1f} MB ({pct:.0f}%)")

    @staticmethod
    def _get_type(message: Message) -> str:
        if message.video: return "video"
        if message.photo: return "photo"
        if message.document: return "document"
        if message.audio: return "audio"
        if message.animation: return "animation"
        if message.sticker: return "sticker"
        if message.voice: return "voice"
        if message.video_note: return "video_note"
        if message.text: return "text"
        return "other"
