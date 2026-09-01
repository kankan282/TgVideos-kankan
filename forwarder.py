import asyncio
import time
import logging
from typing import List, Callable, Optional
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, PeerIdInvalid, ChatAdminRequired

from tg_client import TGClient
from url_parser import parse_tg_link

logger = logging.getLogger(__name__)

class ForwardEngine:

    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    async def run(
        self,
        source: str,
        target: str,
        limit: int = 50,
        content_types: List[str] = None,
        on_progress: Callable = None  # Real-time log callback
    ) -> dict:
        """
        ⚡ Ultra-robust forwarding with:
        - FloodWait auto-handling
        - Specific message ID support
        - Retry logic
        - Real-time progress
        """
        self._cancel = False
        content_types = content_types or ["all"]
        stats = {
            "total": 0, "success": 0, "failed": 0,
            "skipped": 0, "flood_waits": 0, "time": 0
        }
        start = time.time()

        def log(msg, level="info"):
            logger.info(msg)
            if on_progress:
                asyncio.ensure_future(on_progress(msg, level))

        try:
            client = await TGClient.ensure_connected()
            src = parse_tg_link(source)
            tgt = parse_tg_link(target)

            log(f"🔗 Source: {src.chat} (msg_id={src.message_id})")
            log(f"🎯 Target: {tgt.chat}")

            # ── CASE 1: Specific message ID ──
            if src.message_id:
                log(f"📌 Fetching specific message #{src.message_id}...")
                try:
                    msg = await client.get_messages(src.chat, src.message_id)
                    messages = [msg] if msg and not msg.empty else []
                except Exception as e:
                    log(f"❌ Message #{src.message_id} nahi mila: {e}", "error")
                    messages = []

            # ── CASE 2: Channel history ──
            else:
                log(f"📥 Fetching last {limit} messages...")
                messages = []
                async for msg in client.get_chat_history(src.chat, limit=limit):
                    if self._cancel:
                        log("⛔ Cancelled by user", "warn")
                        break
                    messages.append(msg)
                messages.reverse()  # Purane pehle

            stats["total"] = len(messages)
            if not messages:
                log("⚠️ Koi message nahi mila!", "warn")
                stats["time"] = round(time.time() - start, 1)
                return stats

            log(f"📦 {len(messages)} messages mile. Forwarding shuru...")

            # ── Forward each message ──
            for i, msg in enumerate(messages, 1):
                if self._cancel:
                    log("⛔ Cancelled!", "warn")
                    break

                msg_type = self._get_type(msg)
                preview = (msg.text or msg.caption or "")[:40].replace("\n", " ")

                # Content filter
                if "all" not in content_types and msg_type not in content_types:
                    stats["skipped"] += 1
                    log(f"⏭️ [{i}/{len(messages)}] SKIP ({msg_type}): {preview}", "skip")
                    continue

                # Retry loop (max 3 attempts)
                success = False
                for attempt in range(1, 4):
                    try:
                        await self._forward_single(client, msg, tgt.chat)
                        stats["success"] += 1
                        success = True

                        size_info = self._get_size(msg)
                        log(
                            f"✅ [{i}/{len(messages)}] {msg_type.upper()} "
                            f"#{msg.id} {size_info} — {preview}",
                            "success"
                        )
                        break

                    except FloodWait as e:
                        stats["flood_waits"] += 1
                        wait = min(e.value, 120)  # Max 2 min wait
                        log(
                            f"⏳ FLOOD WAIT! {wait} sec rukna padega... "
                            f"(attempt {attempt}/3)",
                            "warn"
                        )
                        await asyncio.sleep(wait)

                    except (PeerIdInvalid, ChatAdminRequired) as e:
                        log(f"❌ [{i}/{len(messages)}] ACCESS ERROR: {e}", "error")
                        stats["failed"] += 1
                        break

                    except Exception as e:
                        err = str(e)[:80]
                        if attempt < 3:
                            log(f"🔄 [{i}/{len(messages)}] Retry {attempt}: {err}", "warn")
                            await asyncio.sleep(3 * attempt)
                        else:
                            log(f"❌ [{i}/{len(messages)}] FAILED: {err}", "error")
                            stats["failed"] += 1

                # Smart delay — FloodWait se bachne ke liye
                if success and not self._cancel:
                    delay = self._smart_delay(msg)
                    if delay > 0:
                        await asyncio.sleep(delay)

            stats["time"] = round(time.time() - start, 1)
            log(
                f"🏁 DONE! ✅{stats['success']} ❌{stats['failed']} "
                f"⏭️{stats['skipped']} ⏳{stats['flood_waits']} "
                f"| {stats['time']}s",
                "success"
            )
            return stats

        except Exception as e:
            log(f"💥 FATAL ERROR: {e}", "error")
            stats["time"] = round(time.time() - start, 1)
            return stats

    async def _forward_single(self, client: Client, msg: Message, target):
        """Single message forward with restricted content handling"""
        try:
            # Pehle direct forward try karo (fastest)
            await msg.forward(target)
        except Exception:
            # Restricted hai → Copy karo
            await self._copy_message(client, msg, target)

    async def _copy_message(self, client: Client, msg: Message, target):
        """Restricted content ko download + re-upload karo"""
        caption = msg.caption or msg.text or ""

        if msg.video:
            path = await msg.download(in_memory=True)
            await client.send_video(
                target, path,
                caption=caption,
                width=msg.video.width,
                height=msg.video.height,
                duration=msg.video.duration,
                supports_streaming=True
            )
        elif msg.document:
            path = await msg.download(in_memory=True)
            await client.send_document(target, path, caption=caption)
        elif msg.photo:
            path = await msg.download(in_memory=True)
            await client.send_photo(target, path, caption=caption)
        elif msg.audio:
            path = await msg.download(in_memory=True)
            await client.send_audio(target, path, caption=caption)
        elif msg.animation:
            path = await msg.download(in_memory=True)
            await client.send_animation(target, path, caption=caption)
        elif msg.voice:
            path = await msg.download(in_memory=True)
            await client.send_voice(target, path)
        elif msg.sticker:
            path = await msg.download(in_memory=True)
            await client.send_sticker(target, path)
        elif msg.video_note:
            path = await msg.download(in_memory=True)
            await client.send_video_note(target, path)
        elif caption:
            await client.send_message(target, caption)
        else:
            raise Exception("Empty message — kuch forward karne ko nahi hai")

    @staticmethod
    def _get_type(msg: Message) -> str:
        if msg.video: return "video"
        if msg.photo: return "photo"
        if msg.document: return "document"
        if msg.audio: return "audio"
        if msg.animation: return "gif"
        if msg.voice: return "voice"
        if msg.sticker: return "sticker"
        if msg.video_note: return "video_note"
        if msg.text: return "text"
        return "other"

    @staticmethod
    def _get_size(msg: Message) -> str:
        """File size nikalo"""
        media = (msg.video or msg.document or msg.audio
                 or msg.animation or msg.voice or msg.video_note)
        if media and hasattr(media, 'file_size') and media.file_size:
            mb = media.file_size / (1024 * 1024)
            if mb >= 1:
                return f"({mb:.1f}MB)"
            else:
                return f"({media.file_size // 1024}KB)"
        return ""

    @staticmethod
    def _smart_delay(msg: Message) -> float:
        """File size ke hisaab se delay do — FloodWait se bachne ke liye"""
        media = (msg.video or msg.document or msg.audio
                 or msg.animation or msg.voice or msg.video_note)
        if media and hasattr(media, 'file_size') and media.file_size:
            mb = media.file_size / (1024 * 1024)
            if mb > 100: return 8      # 100MB+ → 8 sec
            if mb > 50:  return 5      # 50MB+  → 5 sec
            if mb > 10:  return 3      # 10MB+  → 3 sec
        return 1.5  # Default 1.5 sec
