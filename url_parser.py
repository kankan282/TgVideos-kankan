"""
URL Parser — Har tarah ka Telegram link handle karta hai:

✅ https://t.me/channel_name
✅ https://t.me/channel_name/14        ← SPECIFIC MESSAGE
✅ https://t.me/c/1234567890/14        ← PRIVATE CHANNEL + MSG
✅ @channel_name
✅ -1001234567890                       ← Direct ID
✅ https://t.me/+AbCdEfGh              ← Invite Link
"""

import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class ParsedTarget:
    chat: str          # Channel username ya ID
    message_id: Optional[int] = None  # Specific message ID (agar link me hai)
    is_private: bool = False

def parse_tg_link(input_str: str) -> ParsedTarget:
    s = input_str.strip()

    # 1) Direct ID: -1001234567890
    if s.lstrip("-").isdigit():
        return ParsedTarget(chat=int(s))

    # 2) @username
    if s.startswith("@"):
        return ParsedTarget(chat=s)

    # 3) t.me links
    if "t.me/" in s:
        after = s.split("t.me/")[-1].split("?")[0].rstrip("/")

        # 3a) Private channel: t.me/c/1234567890/14
        m = re.match(r"c/(\d+)(?:/(\d+))?", after)
        if m:
            chat_id = int(f"-100{m.group(1)}")
            msg_id = int(m.group(2)) if m.group(2) else None
            return ParsedTarget(chat=chat_id, message_id=msg_id, is_private=True)

        # 3b) Public: t.me/channel_name/14
        m = re.match(r"([a-zA-Z0-9_]+)(?:/(\d+))?", after)
        if m:
            username = m.group(1)
            msg_id = int(m.group(2)) if m.group(2) else None
            if username.startswith("+"):
                return ParsedTarget(chat=s, is_private=True)
            return ParsedTarget(chat=f"@{username}", message_id=msg_id)

    # 4) Fallback
    return ParsedTarget(chat=s)
